const std = @import("std");
const fangz = @import("fangz");

pub fn register(root: *fangz.Command) !void {
    _ = try root.addSubcommand(.{
        .name = "hello",
        .description = "greet me",
    });

    // hello_cmd.setHooks(.{
    //     .run = std.debug.print("Hello, world!\n", .{}),
    // });
}
