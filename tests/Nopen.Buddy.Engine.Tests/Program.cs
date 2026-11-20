using System.Text.Json;
using Nopen.Buddy.Engine;

static void Equal<T>(T expected, T actual)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
        throw new InvalidOperationException($"Expected {expected}, got {actual}.");
}

static async Task State(BuddyEngine engine, BuddyEvent @event, string expected) =>
    Equal(expected, (await engine.SendAsync(@event)).State);

static async Task WithEngine(Func<BuddyEngine, Task> test, IActionExecutor? executor = null)
{
    var dir = Directory.CreateTempSubdirectory().FullName;
    try
    {
        using var store = new EngineStateStore(dir);
        await using var engine = new BuddyEngine(store, executor ?? new MockExecutor());
        await test(engine);
    }
    finally { Directory.Delete(dir, recursive: true); }
}

static async Task<string> CompleteFixture(BuddyEngine engine, string key)
{
    await State(engine, new TaskRequested("fixture", key), "NEEDS_APPROVAL");
    await State(engine, new ApprovalGranted(key), "RUNNING");
    var result = await engine.SendAsync(new WaitRequested(key));
    Equal("DONE", result.State);
    return result.Checkpoint?.Result ?? "";
}

static async Task Race(BuddyEvent safety, string expected)
{
    var executor = new HeldExecutor();
    await WithEngine(async engine =>
    {
        await State(engine, new TaskRequested("fixture", "first"), "NEEDS_APPROVAL");
        await State(engine, new ApprovalGranted("first"), "RUNNING");
        await executor.Entered.Task.WaitAsync(TimeSpan.FromSeconds(3));
        var wait = engine.SendAsync(new WaitRequested("first"));
        // Queue a safety event while a deliberately non-cooperative fixture is active.
        await State(engine, safety, expected);
        await State(engine, safety, expected);
        Equal(true, executor.Token.IsCancellationRequested);
        await State(engine, new TaskRequested("fixture", "second"), "BLOCKED");
        if (safety is not PermissionRevoked)
        {
            await State(engine, new ResumeRequested(), "RUNNING");
            await State(engine, new TaskRequested("fixture", "second"), "BLOCKED");
        }
        executor.Release.TrySetResult("fixture-completed");
        Equal(null, (await wait).Checkpoint);
        await State(engine, new HandoffRequested("first"), "BLOCKED");
        if (safety is PermissionRevoked)
            await State(engine, new ResumeRequested(), "BLOCKED");
        Equal(1, executor.Starts);
    }, executor);
}

static async Task Restart()
{
    var dir = Directory.CreateTempSubdirectory().FullName;
    try
    {
        using (var store = new EngineStateStore(dir))
        {
            await using var engine = new BuddyEngine(store, new MockExecutor());
            Equal("fixture-completed", await CompleteFixture(engine, "one"));
            await State(engine, new StopRequested(), "PAUSED");
        }
        using (var store = new EngineStateStore(dir))
        {
            await using var engine = new BuddyEngine(store, new FailingExecutor());
            await State(engine, new StatusRequested(), "PAUSED");
            await State(engine, new TaskRequested("fixture", "one"), "DONE");
            await State(engine, new TaskRequested("fixture", "two"), "PAUSED");
            await State(engine, new ResumeRequested(), "IDLE");
            await State(engine, new PermissionRevoked(), "BLOCKED");
        }
        using (var store = new EngineStateStore(dir))
        {
            await using var engine = new BuddyEngine(store, new FailingExecutor());
            await State(engine, new ResumeRequested(), "BLOCKED");
            await State(engine, new HandoffRequested("one"), "DONE");
        }
    }
    finally { Directory.Delete(dir, recursive: true); }
}

static async Task CorruptState()
{
    var dir = Directory.CreateTempSubdirectory().FullName;
    try
    {
        using (var store = new EngineStateStore(dir))
        {
            await using var engine = new BuddyEngine(store, new MockExecutor());
            await CompleteFixture(engine, "one");
        }
        var path = Path.Combine(dir, "engine-state.json");
        const string invalid = """{"version":1,"checkpoints":[]}""";
        File.WriteAllText(path, invalid);
        try
        {
            using var store = new EngineStateStore(dir);
            await using var engine = new BuddyEngine(store, new MockExecutor());
        }
        catch (JsonException)
        {
            Equal(invalid, File.ReadAllText(path));
            return;
        }
        throw new InvalidOperationException("Malformed state was admitted.");
    }
    finally { Directory.Delete(dir, recursive: true); }
}

static async Task FailedCommit()
{
    var root = Directory.CreateTempSubdirectory().FullName;
    try
    {
        using var store = new EngineStateStore(root);
        await using var engine = new BuddyEngine(store, new MockExecutor());
        Directory.CreateDirectory(Path.Combine(root, "engine-state.json"));
        await State(engine, new TaskRequested("fixture", "one"), "NEEDS_APPROVAL");
        await State(engine, new ApprovalGranted("one"), "RUNNING");
        await State(engine, new WaitRequested("one"), "BLOCKED");
        await State(engine, new StatusRequested(), "BLOCKED");
        await State(engine, new ResumeRequested(), "BLOCKED");
        Equal(0, Directory.GetFiles(root, ".engine-*.tmp").Length);
    }
    finally { Directory.Delete(root, recursive: true); }
}

(string Name, Func<Task> Test)[] cases =
[
    ("parser permits only deterministic vocabulary", () =>
    {
        Equal<BuddyEvent?>(new TaskRequested("fixture", "a"), ConsoleIntent.Parse("kurgu görev çalıştır a"));
        Equal<BuddyEvent?>(new ResumeRequested(), ConsoleIntent.Parse("devam"));
        Equal<BuddyEvent?>(null, ConsoleIntent.Parse("open a browser and capture the screen"));
        Equal<BuddyEvent?>(null, ConsoleIntent.Parse("kurgu görev çalıştır ../a"));
        return Task.CompletedTask;
    }),
    ("policy denies every system capability", () =>
    {
        var gate = new PolicyGate();
        foreach (var capability in Enum.GetValues<Capability>().Where(cap => cap != Capability.Fixture))
            Equal("BLOCKED", gate.Denial(new("fixture", "one", capability), false, false, "one"));
        Equal("NEEDS_APPROVAL", gate.Denial(new("fixture", "one", Capability.Fixture), false, false, null));
        return Task.CompletedTask;
    }),
    ("no implicit or mismatched approval", () => WithEngine(async engine =>
    {
        await State(engine, new TaskRequested("fixture", "one"), "NEEDS_APPROVAL");
        await State(engine, new TimeTick(), "NEEDS_APPROVAL");
        await State(engine, new ApprovalGranted("other"), "BLOCKED");
        await State(engine, new HandoffRequested("one"), "BLOCKED");
        await State(engine, new UserIntervention(), "PAUSED");
        await State(engine, new ResumeRequested(), "IDLE");
        await State(engine, new ApprovalGranted("one"), "BLOCKED");
    })),
    ("completed result is deterministic and deduplicated", () => WithEngine(async engine =>
    {
        Equal("fixture-completed", await CompleteFixture(engine, "one"));
        await State(engine, new TaskRequested("fixture", "one"), "DONE");
        await State(engine, new ApprovalGranted("one"), "BLOCKED");
        await State(engine, new HandoffRequested("one"), "DONE");
    })),
    ("stop cancels and prevents overlapping starts", () => Race(new StopRequested(), "PAUSED")),
    ("intervention cancels and prevents overlapping starts", () => Race(new UserIntervention(), "PAUSED")),
    ("revocation cancels and resume does not regrant", () => Race(new PermissionRevoked(), "BLOCKED")),
    ("checkpoint and safety state survive restart", Restart),
    ("executor error produces no checkpoint and allows fresh retry", () => WithEngine(async engine =>
    {
        await State(engine, new TaskRequested("fixture", "one"), "NEEDS_APPROVAL");
        await State(engine, new ApprovalGranted("one"), "RUNNING");
        await State(engine, new WaitRequested("one"), "BLOCKED");
        await State(engine, new HandoffRequested("one"), "BLOCKED");
        Equal("fixture-completed", await CompleteFixture(engine, "one"));
    }, new FailingExecutor())),
    ("corrupt durable state fails closed", CorruptState),
    ("failed atomic commit latches the engine closed", FailedCommit),
];

foreach (var (name, test) in cases)
{
    await test().WaitAsync(TimeSpan.FromSeconds(10));
    Console.WriteLine($"PASS {name}");
}
Console.WriteLine($"PASS {cases.Length}/{cases.Length}");

sealed class HeldExecutor : IActionExecutor
{
    internal TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal TaskCompletionSource<string> Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal CancellationToken Token { get; private set; }
    internal int Starts { get; private set; }

    public ValueTask<string> ExecuteAsync(SkillPlan plan, CancellationToken cancellationToken)
    {
        Starts++;
        Token = cancellationToken;
        Entered.TrySetResult();
        return new(Release.Task);
    }
}

sealed class FailingExecutor : IActionExecutor
{
    private bool failed;

    public ValueTask<string> ExecuteAsync(SkillPlan plan, CancellationToken cancellationToken)
    {
        if (failed)
            return ValueTask.FromResult("fixture-completed");
        failed = true;
        throw new IOException("Synthetic executor failure.");
    }
}
