using System.Text.Json;
using System.Text.Json.Serialization;

namespace Nopen.Buddy.Engine;

internal sealed record DurableState(
    [property: JsonRequired] int Version,
    [property: JsonRequired] bool Paused,
    [property: JsonRequired] bool Revoked,
    [property: JsonRequired] Checkpoint[] Checkpoints);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(DurableState))]
[JsonSerializable(typeof(Reply))]
internal sealed partial class EngineJson : JsonSerializerContext;

public sealed class EngineStateStore : IDisposable
{
    internal const int MaxCheckpoints = 4096;
    private const UnixFileMode DirectoryMode = UnixFileMode.UserRead | UnixFileMode.UserWrite |
                                               UnixFileMode.UserExecute;
    private const UnixFileMode FileModePrivate = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    private readonly string directory;
    private readonly string statePath;
    private readonly FileStream owner;

    public EngineStateStore(string directory)
    {
        this.directory = Path.TrimEndingDirectorySeparator(Path.GetFullPath(directory));
        if (Path.GetFileName(this.directory) == "nopen-studio-core" ||
            File.Exists(Path.Combine(this.directory, "memory.sqlite3")))
            throw new IOException("Use a dedicated C# engine state directory.");
        if (OperatingSystem.IsWindows())
            Directory.CreateDirectory(this.directory);
        else
            Directory.CreateDirectory(this.directory, DirectoryMode);
        RejectLink(this.directory);
        if (!OperatingSystem.IsWindows() && File.GetUnixFileMode(this.directory) != DirectoryMode)
            throw new IOException("Engine state directory must have mode 0700.");
        statePath = Path.Combine(this.directory, "engine-state.json");
        var lockPath = Path.Combine(this.directory, "engine.lock");
        RejectLink(lockPath);
        owner = new FileStream(lockPath, PrivateOptions(FileMode.OpenOrCreate));
    }

    private static void RejectLink(string path)
    {
        var info = new FileInfo(path);
        if (info.LinkTarget is not null)
            throw new IOException("Engine state paths cannot be symbolic links.");
    }

    private static FileStreamOptions PrivateOptions(FileMode mode)
    {
        var options = new FileStreamOptions
        {
            Mode = mode, Access = FileAccess.Write, Share = FileShare.None
        };
        if (!OperatingSystem.IsWindows())
            options.UnixCreateMode = FileModePrivate;
        return options;
    }

    internal DurableState Load()
    {
        RejectLink(statePath);
        if (Directory.Exists(statePath))
            throw new InvalidDataException("Expected an engine checkpoint file.");
        if (!File.Exists(statePath))
            return new(1, false, false, []);
        var info = new FileInfo(statePath);
        if (info.Length > 1024 * 1024 ||
            (!OperatingSystem.IsWindows() && File.GetUnixFileMode(statePath) != FileModePrivate))
            throw new InvalidDataException("Unsafe engine checkpoint file.");
        using var stream = File.OpenRead(statePath);
        var state = JsonSerializer.Deserialize(stream, EngineJson.Default.DurableState);
        if (state is null || state.Version != 1 || state.Checkpoints is null ||
            state.Checkpoints.Length > MaxCheckpoints ||
            state.Checkpoints.Any(c => c is null || c.Key is null || !SkillRegistry.IsKey(c.Key) ||
                                       c.Skill != "fixture" || c.Result != "fixture-completed") ||
            state.Checkpoints.Select(c => c.Key).Distinct(StringComparer.Ordinal).Count() != state.Checkpoints.Length)
            throw new InvalidDataException("Invalid engine checkpoint schema.");
        return state;
    }

    internal void Save(DurableState next)
    {
        var temporary = Path.Combine(directory, $".engine-{Guid.NewGuid():N}.tmp");
        try
        {
            using (var output = new FileStream(temporary, PrivateOptions(FileMode.CreateNew)))
            {
                JsonSerializer.Serialize(output, next, EngineJson.Default.DurableState);
                output.Flush(flushToDisk: true);
            }
            File.Move(temporary, statePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }

    public static string Format(Reply value) => JsonSerializer.Serialize(value, EngineJson.Default.Reply);
    public void Dispose() => owner.Dispose();
}
