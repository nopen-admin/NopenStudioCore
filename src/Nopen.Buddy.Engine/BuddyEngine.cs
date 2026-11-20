using System.Threading.Channels;

namespace Nopen.Buddy.Engine;

public sealed class BuddyEngine : IAsyncDisposable
{
    private sealed record Envelope(BuddyEvent Event, TaskCompletionSource<Reply> Response);
    private sealed record ActionCompleted(long Attempt, string? Result) : BuddyEvent;
    private sealed record Shutdown : BuddyEvent;
    private sealed class Active(long attempt, SkillPlan plan)
    {
        internal long Attempt { get; } = attempt;
        internal SkillPlan Plan { get; } = plan;
        internal CancellationTokenSource Cancellation { get; } = new();
        internal Task CancellationDispatch { get; set; } = Task.CompletedTask;
        internal TaskCompletionSource<Reply>? Waiter { get; set; }
    }

    private readonly Channel<Envelope> events = Channel.CreateBounded<Envelope>(
        new BoundedChannelOptions(64) { SingleReader = true, FullMode = BoundedChannelFullMode.Wait });
    private readonly IActionExecutor executor;
    private readonly EngineStateStore store;
    private readonly SkillRegistry skills = new();
    private readonly PolicyGate policy = new();
    private readonly Task loop;
    private DurableState state;
    private SkillPlan? pending;
    private Active? active;
    private long attempt;
    private bool closing;
    private bool faulted;
    private string terminal = "IDLE";

    public BuddyEngine(EngineStateStore store, IActionExecutor executor)
    {
        this.store = store;
        this.executor = executor;
        state = store.Load();
        loop = ConsumeAsync();
    }

    public async Task<Reply> SendAsync(BuddyEvent message)
    {
        var response = new TaskCompletionSource<Reply>(TaskCreationOptions.RunContinuationsAsynchronously);
        await events.Writer.WriteAsync(new(message, response)).ConfigureAwait(false);
        return await response.Task.ConfigureAwait(false);
    }

    private async Task ConsumeAsync()
    {
        await foreach (var item in events.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            try
            {
                var reply = Reduce(item);
                if (reply is not null)
                    item.Response.TrySetResult(reply);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException)
            {
                faulted = true;
                Cancel();
                item.Response.TrySetResult(new("BLOCKED", "Local checkpoint unavailable; restart required."));
                if (closing && active is null)
                    events.Writer.TryComplete();
            }
        }
    }

    private Reply? Reduce(Envelope item) => item.Event switch
    {
        ActionCompleted result => Complete(result),
        Shutdown => Close(),
        StatusRequested or TimeTick => Current(),
        HandoffRequested request => Find(request.Key),
        _ when closing || faulted => new("BLOCKED", "Engine unavailable."),
        TaskRequested request => Request(request),
        ApprovalGranted approval => Approve(approval.Key),
        WaitRequested wait => Wait(wait.Key, item.Response),
        UserIntervention or StopRequested => ChangeControl(paused: true, state.Revoked),
        PermissionRevoked => ChangeControl(state.Paused, revoked: true),
        ResumeRequested => ChangeControl(paused: false, state.Revoked),
        _ => new("UNSUPPORTED", "Unknown event."),
    };

    private Reply Request(TaskRequested request)
    {
        var plan = skills.Plan(request.Skill, request.Key);
        if (plan is null)
            return new("UNSUPPORTED", "Unknown skill or invalid task key.");
        var previous = Find(request.Key);
        if (previous.Checkpoint is not null)
            return previous;
        if (active is not null || pending is not null)
            return pending?.Key == request.Key
                ? new("NEEDS_APPROVAL", "Awaiting explicit approval for this task key.")
                : new("BLOCKED", "An action or approval is already pending.");
        if (state.Checkpoints.Length >= EngineStateStore.MaxCheckpoints)
            return new("BLOCKED", "Local checkpoint capacity reached.");
        var denial = policy.Denial(plan, state.Paused, state.Revoked, null);
        if (denial != "NEEDS_APPROVAL")
            return Current();
        pending = plan;
        return Current();
    }

    private Reply Approve(string key)
    {
        if (pending is not { } plan || active is not null || key != plan.Key)
            return new("BLOCKED", "Approval does not match a pending action.");
        var denial = policy.Denial(plan, state.Paused, state.Revoked, key);
        if (denial is not null)
            return new(denial, "Policy denied this action.");
        pending = null;
        var work = new Active(++attempt, plan);
        active = work;
        _ = Task.Run(() => ExecuteAsync(work));
        return new("RUNNING", "Fixture accepted.");
    }

    private async Task ExecuteAsync(Active work)
    {
        string? result = null;
        try
        {
            work.Cancellation.Token.ThrowIfCancellationRequested();
            result = await executor.ExecuteAsync(work.Plan, work.Cancellation.Token).ConfigureAwait(false);
        }
        catch (Exception)
        {
            // An executor fault is represented without exception text or a checkpoint.
        }
        await SendAsync(new ActionCompleted(work.Attempt, result)).ConfigureAwait(false);
    }

    private Reply Complete(ActionCompleted result)
    {
        if (active is not { } work || work.Attempt != result.Attempt)
            return Current();
        active = null;
        try
        {
            var cancelled = work.Cancellation.IsCancellationRequested;
            if (cancelled || closing || faulted)
            {
                terminal = "IDLE";
                return Current();
            }
            if (result.Result != "fixture-completed")
            {
                terminal = "BLOCKED";
                return Current();
            }
            var checkpoint = new Checkpoint(work.Plan.Key, work.Plan.Skill, result.Result);
            Persist(state with { Checkpoints = [.. state.Checkpoints, checkpoint] });
            terminal = "DONE";
            return new("DONE", "Checkpoint committed.", checkpoint);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            faulted = true;
            throw;
        }
        finally
        {
            _ = DisposeCancellationAsync(work);
            if (work.Waiter is { } waiter)
            {
                var outcome = Find(work.Plan.Key);
                waiter.TrySetResult(outcome.Checkpoint is not null ? outcome : Current());
            }
            if (closing)
                events.Writer.TryComplete();
        }
    }

    private Reply? Wait(string key, TaskCompletionSource<Reply> response)
    {
        if (active is not { } work || work.Plan.Key != key)
            return Find(key);
        if (work.Waiter is not null)
            return new("BLOCKED", "An action waiter is already registered.");
        work.Waiter = response;
        return null;
    }

    private Reply Find(string key)
    {
        var item = state.Checkpoints.FirstOrDefault(c => c.Key == key);
        return item is null ? new("BLOCKED", "Checkpoint not found.") : new("DONE", "Checkpoint found.", item);
    }

    private Reply Current()
    {
        if (faulted || state.Revoked || closing)
            return new("BLOCKED", "Execution is disabled.");
        if (state.Paused)
            return new("PAUSED", "Explicit resume required.");
        if (active is not null)
            return new("RUNNING", "One action is active or draining.");
        if (pending is not null)
            return new("NEEDS_APPROVAL", "An action awaits explicit approval.");
        return new(terminal, "No active action.");
    }

    private Reply ChangeControl(bool paused, bool revoked)
    {
        if (paused || revoked)
            Cancel();
        if (state.Paused != paused || state.Revoked != revoked)
            Persist(state with { Paused = paused, Revoked = revoked });
        if (terminal == "BLOCKED")
            terminal = "IDLE";
        return Current();
    }

    private void Persist(DurableState next)
    {
        store.Save(next);
        state = next;
    }

    private void Cancel()
    {
        pending = null;
        // Do not run a backend's cancellation callbacks on the event consumer.
        if (active is { } work && !work.Cancellation.IsCancellationRequested)
            work.CancellationDispatch = work.Cancellation.CancelAsync();
    }

    private static async Task DisposeCancellationAsync(Active work)
    {
        try
        {
            await work.CancellationDispatch.ConfigureAwait(false);
        }
        catch (AggregateException)
        {
            // An executor callback cannot override the cancellation decision.
        }
        finally { work.Cancellation.Dispose(); }
    }

    private Reply Close()
    {
        closing = true;
        Cancel();
        if (active is null)
            events.Writer.TryComplete();
        return Current();
    }

    public async ValueTask DisposeAsync()
    {
        await SendAsync(new Shutdown()).ConfigureAwait(false);
        await loop.ConfigureAwait(false);
    }
}
