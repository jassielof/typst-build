const std = @import("std");
const fangz = @import("fangz");

pub fn register(root: *fangz.Command) !void {
    const cmd = try root.addSubcommand(.{
        .name = "info",
        .description = "information",
    });

    cmd.setHelpOnEmptyArgs(true);

    try cmd.addPositional(.{
        .name = "package name",
        .description = "Name of the package to display information about",
    });
}
