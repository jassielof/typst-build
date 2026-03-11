const fangz = @import("fangz");

pub fn register(root: *fangz.Command) !void {
    const cmd = try root.addSubcommand(.{
        .name = "uninstall",
        .description = "Uninstall a package.",
    });

    cmd.setHooks(.{});
}
