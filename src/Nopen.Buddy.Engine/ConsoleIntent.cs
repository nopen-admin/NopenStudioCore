namespace Nopen.Buddy.Engine;

public static class ConsoleIntent
{
    public static BuddyEvent? Parse(string line)
    {
        var words = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        return words switch
        {
            ["durum"] => new StatusRequested(),
            ["duraklat"] => new UserIntervention(),
            ["devam"] => new ResumeRequested(),
            ["dur"] => new StopRequested(),
            ["izni-iptal"] => new PermissionRevoked(),
            ["kontrol"] => new TimeTick(),
            ["kurgu", "görev", "çalıştır", var key] when SkillRegistry.IsKey(key) =>
                new TaskRequested("fixture", key),
            ["onayla", var key] when SkillRegistry.IsKey(key) => new ApprovalGranted(key),
            ["handoff", var key] when SkillRegistry.IsKey(key) => new HandoffRequested(key),
            _ => null,
        };
    }
}
