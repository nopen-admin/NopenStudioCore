using System.Runtime.InteropServices;
using Nopen.Buddy.Engine;

namespace Nopen.Buddy.Cli;

internal static partial class LegacySnapshot
{
    private const string Library = "libsqlite3.so.0";
    private const int ReadOnlyUri = 0x01 | 0x40;
    private const int ApplicationId = 0x4E534343;

    private const string StatusSql = """
        SELECT json_object('format','nopen-buddy-w003-readonly-v1','mode',mode,
            'tasks',(SELECT count(*) FROM tasks),'queued_actions',
            (SELECT count(*) FROM actions WHERE status='QUEUED')) FROM control WHERE id=1
        """;
    private const string TaskJson = """
        json_object('id',id,'goal',goal,'state',state,'summary',summary,'unknowns',unknowns,
                    'next_step',next_step,'priority',priority,'deadline',deadline)
        """;
    private const string EventJson = """
        json_object('seq',seq,'occurred_at',occurred_at,'task_id',task_id,
                    'kind',kind,'source',source,'detail',json(detail))
        """;
    private const string CheckpointJson = """
        json_object('action_id',action_id,'task_id',task_id,'event_seq',event_seq,'snapshot',json(snapshot))
        """;
    private const string ExportSql = $"""
        SELECT json_object('format','nopen-buddy-w003-readonly-v1',
            'mode',(SELECT mode FROM control WHERE id=1),
            'tasks',(SELECT json_group_array(json(item)) FROM
                (SELECT {TaskJson} AS item FROM tasks ORDER BY id)),
            'events',(SELECT json_group_array(json(item)) FROM
                (SELECT {EventJson} AS item FROM events ORDER BY seq)),
            'actions',(SELECT json_group_array(json(item)) FROM
                (SELECT json_object('seq',seq,'id',id,'task_id',task_id,'kind',kind,
                                    'payload',json(payload),'status',status) AS item FROM actions ORDER BY seq)),
            'permissions',(SELECT json_group_object(capability,decision) FROM permissions),
            'checkpoints',(SELECT json_group_array(json(item)) FROM
                (SELECT {CheckpointJson} AS item FROM checkpoints ORDER BY event_seq)))
        """;
    private const string HandoffSql = $"""
        SELECT json_object('format','nopen-buddy-w003-readonly-v1',
            'task',json({TaskJson}),
            'history',(SELECT json_group_array(json(item)) FROM
                (SELECT {EventJson} AS item FROM events WHERE task_id=?1 ORDER BY seq)),
            'last_checkpoint',json((SELECT {CheckpointJson} FROM checkpoints
                WHERE task_id=?1 ORDER BY event_seq DESC LIMIT 1)))
        FROM tasks WHERE id=?1
        """;

    internal static string Read(string filename, string operation, string? key)
    {
        if (!OperatingSystem.IsLinux())
            throw new PlatformNotSupportedException("Legacy fixture reading currently requires Linux.");
        var path = Path.GetFullPath(filename);
        var info = new FileInfo(path);
        if (info.Name == "memory.sqlite3" || !info.Exists || info.LinkTarget is not null || info.Length is <= 0 or > 32 * 1024 * 1024 ||
            new[] { "-wal", "-shm", "-journal" }.Any(suffix =>
                File.Exists(path + suffix) || new FileInfo(path + suffix).LinkTarget is not null))
            throw new InvalidDataException("Provide a closed, standalone synthetic SQLite snapshot.");

        using (var header = File.OpenRead(path))
        {
            header.Position = 18;
            // A raw copy of a WAL database can silently omit committed pages.
            if (header.ReadByte() != 1 || header.ReadByte() != 1)
                throw Invalid();
        }

        var uri = "file:" + string.Join('/', path.Split('/').Select(Uri.EscapeDataString)) +
                  "?immutable=1";
        var code = sqlite3_open_v2(uri, out var db, ReadOnlyUri, nint.Zero);
        try
        {
            if (code != 0 || sqlite3_db_readonly(db, "main") != 1)
                throw Invalid();
            sqlite3_limit(db, 0, 4 * 1024 * 1024); // SQLITE_LIMIT_LENGTH
            Execute(db, "PRAGMA trusted_schema=OFF");
            if (Query(db, "PRAGMA application_id") != ApplicationId.ToString() ||
                Query(db, "PRAGMA user_version") != "2" ||
                Query(db, "PRAGMA quick_check(1)") != "ok" ||
                Query(db, """
                    SELECT count(*) FROM pragma_table_list WHERE schema='main' AND type='table' AND name IN
                        ('control','permissions','tasks','events','actions','checkpoints')
                    """) != "6")
                throw Invalid();

            foreach (var projection in new[] { StatusSql, ExportSql, HandoffSql })
                sqlite3_finalize(Prepare(db, projection));

            return operation switch
            {
                "status" => Query(db, StatusSql),
                "export" => Query(db, ExportSql),
                "handoff" when key is not null && SkillRegistry.IsKey(key) => Query(db, HandoffSql, key),
                _ => throw Invalid(),
            };
        }
        finally
        {
            if (db != nint.Zero)
                sqlite3_close(db);
        }
    }

    private static InvalidDataException Invalid() => new("Invalid or incompatible W003 fixture.");

    private static nint Prepare(nint db, string sql)
    {
        if (sqlite3_prepare_v2(db, sql, -1, out var statement, nint.Zero) != 0)
            throw Invalid();
        return statement;
    }

    private static void Execute(nint db, string sql)
    {
        var statement = Prepare(db, sql);
        try
        {
            if (sqlite3_step(statement) != 101) // SQLITE_DONE
                throw Invalid();
        }
        finally { sqlite3_finalize(statement); }
    }

    private static string Query(nint db, string sql, string? key = null)
    {
        var statement = Prepare(db, sql);
        try
        {
            if (key is not null && sqlite3_bind_text(statement, 1, key, -1, new nint(-1)) != 0)
                throw Invalid();
            if (sqlite3_step(statement) != 100) // SQLITE_ROW
                throw Invalid();
            return Marshal.PtrToStringUTF8(sqlite3_column_text(statement, 0)) ?? throw Invalid();
        }
        finally { sqlite3_finalize(statement); }
    }

    [LibraryImport(Library, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int sqlite3_open_v2(string filename, out nint db, int flags, nint vfs);
    [LibraryImport(Library)]
    private static partial int sqlite3_close(nint db);
    [LibraryImport(Library, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int sqlite3_db_readonly(nint db, string database);
    [LibraryImport(Library)]
    private static partial int sqlite3_limit(nint db, int category, int limit);
    [LibraryImport(Library, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int sqlite3_prepare_v2(nint db, string sql, int bytes, out nint statement, nint tail);
    [LibraryImport(Library, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int sqlite3_bind_text(nint statement, int index, string value, int length, nint destructor);
    [LibraryImport(Library)]
    private static partial int sqlite3_step(nint statement);
    [LibraryImport(Library)]
    private static partial nint sqlite3_column_text(nint statement, int column);
    [LibraryImport(Library)]
    private static partial int sqlite3_finalize(nint statement);
}
