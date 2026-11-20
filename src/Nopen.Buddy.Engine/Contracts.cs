namespace Nopen.Buddy.Engine;

public abstract record BuddyEvent;
public sealed record TaskRequested(string Skill, string Key) : BuddyEvent;
public sealed record UserIntervention : BuddyEvent;
public sealed record PermissionRevoked : BuddyEvent;
public sealed record StopRequested : BuddyEvent;
public sealed record TimeTick : BuddyEvent;
public sealed record ResumeRequested : BuddyEvent;
public sealed record ApprovalGranted(string Key) : BuddyEvent;
public sealed record StatusRequested : BuddyEvent;
public sealed record HandoffRequested(string Key) : BuddyEvent;
public sealed record WaitRequested(string Key) : BuddyEvent;

public enum Capability { Fixture, Screen, Pointer, Keyboard, Microphone, Network }
public sealed record SkillPlan(string Skill, string Key, Capability Capability);
public sealed record Checkpoint(string Key, string Skill, string Result);
public sealed record Reply(string State, string Message, Checkpoint? Checkpoint = null);

public sealed class SkillRegistry
{
    public SkillPlan? Plan(string skill, string key) =>
        skill == "fixture" && IsKey(key) ? new(skill, key, Capability.Fixture) : null;

    public static bool IsKey(string key) =>
        key.Length is >= 1 and <= 64 && char.IsAsciiLetterOrDigit(key[0]) &&
        key.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '_' or '-');
}

public sealed class PolicyGate
{
    public string? Denial(SkillPlan plan, bool paused, bool revoked, string? approval)
    {
        if (plan.Capability != Capability.Fixture || revoked)
            return "BLOCKED";
        if (paused)
            return "PAUSED";
        return approval == plan.Key ? null : "NEEDS_APPROVAL";
    }
}

// Executors prepare a result. Only the engine can commit a checkpoint.
public interface IActionExecutor
{
    ValueTask<string> ExecuteAsync(SkillPlan plan, CancellationToken cancellationToken);
}

public sealed class MockExecutor : IActionExecutor
{
    public ValueTask<string> ExecuteAsync(SkillPlan plan, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (plan.Capability != Capability.Fixture || plan.Skill != "fixture")
            throw new InvalidOperationException("Only the built-in fixture is supported.");
        return ValueTask.FromResult("fixture-completed");
    }
}
