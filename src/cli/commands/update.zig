const fangz = @import("fangz");

pub fn register(root: *fangz.Command) !void {
    const cmd = try root.addSubcommand(.{
        .name = "update",
        .description = "Update or check for updates on installed packages. Only applies to locally installed packages, not Typst installed packages.",
    });

    cmd.setHooks(.{});
}
