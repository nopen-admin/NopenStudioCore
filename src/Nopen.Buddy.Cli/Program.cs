using System.Runtime.InteropServices;
using System.Text.Json;
using Nopen.Buddy.Cli;
using Nopen.Buddy.Engine;

static void Print(Reply reply) => Console.WriteLine(EngineStateStore.Format(reply));

static int BadCommand()
{
    Print(new("UNSUPPORTED",
        "Use --state DIR status|run|demo KEY --approve, or --sqlite-copy FILE status|export|handoff KEY."));
    return 2;
}

static async Task<int> RunAsync(BuddyEngine engine)
{
    using var cancelled = new CancellationTokenSource();
    ConsoleCancelEventHandler cancel = (_, e) =>
    {
        e.Cancel = true;
        cancelled.Cancel();
    };
    Console.CancelKeyPress += cancel;
    using var terminate = OperatingSystem.IsWindows() ? null : PosixSignalRegistration.Create(
        PosixSignal.SIGTERM, context => { context.Cancel = true; cancelled.Cancel(); });
    try
    {
        Print(await engine.SendAsync(new StatusRequested()));
        while (await Task.Run(Console.ReadLine).WaitAsync(cancelled.Token) is { } line && line != "çık")
        {
            var intent = ConsoleIntent.Parse(line);
            Print(intent is null
                ? new("UNSUPPORTED", "Supported: durum, duraklat, devam, dur, izni-iptal, kontrol, kurgu görev çalıştır KEY, onayla KEY, handoff KEY, çık.")
                : await engine.SendAsync(intent));
        }
    }
    catch (OperationCanceledException) when (cancelled.IsCancellationRequested) { }
    finally
    {
        await engine.SendAsync(new StopRequested());
        Console.CancelKeyPress -= cancel;
    }
    return 0;
}

try
{
    if (args is ["--sqlite-copy", _, "status" or "export"] or
                ["--sqlite-copy", _, "handoff", _])
    {
        Console.WriteLine(LegacySnapshot.Read(args[1], args[2], args.Length == 4 ? args[3] : null));
        return 0;
    }
    if (args is not (["--state", _, "status" or "run"] or ["--state", _, "demo", _, "--approve"]))
        return BadCommand();

    using var store = new EngineStateStore(args[1]);
    await using var engine = new BuddyEngine(store, new MockExecutor());
    switch (args[2])
    {
        case "status":
            Print(await engine.SendAsync(new StatusRequested()));
            return 0;
        case "run":
            return await RunAsync(engine);
        default:
            var key = args[3];
            var result = await engine.SendAsync(new TaskRequested("fixture", key));
            if (result.State == "NEEDS_APPROVAL")
            {
                result = await engine.SendAsync(new ApprovalGranted(key));
                if (result.State == "RUNNING")
                    result = await engine.SendAsync(new WaitRequested(key));
            }
            Print(result);
            return result.State == "DONE" ? 0 : 1;
    }
}
catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException or JsonException or
                              DllNotFoundException or EntryPointNotFoundException or
                              PlatformNotSupportedException or ArgumentException)
{
    Print(new("BLOCKED", "Local state or synthetic SQLite snapshot unavailable or invalid."));
    return 1;
}
