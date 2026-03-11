const fangz = @import("fangz");

pub fn register(root: *fangz.Command) !void {
    const cmd = try root.addSubcommand(.{
        .name = "pack",
        .description = "Package the project for publishing.",
    });

    try cmd.addPositional(.{
        .name = "manifest",
        .description = "Path to the manifest file to package (or its directory), if it's not provided, it'll attempt to look in the current directory.",
    });

    try cmd.addFlag(.{
        .name = "output",
        .short = 'o',
        .description = "The output directory to place the packaged artifact.",
        .default_value = .{ .string = "out" },
    });

    try cmd.addFlag(.{
        .name = "namespace",
        .short = 'n',
        .description = "Namespace for the package.",
        .default_value = .{ .string = "local" },
    });

    // cmd.setHooks(.{});
}

fn run(ctx: *fangz.ParseContext) !void {
    const allocator = ctx.allocator;
    
}
