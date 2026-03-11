const std = @import("std");
const semver = std.SemanticVersion;

const fangz = @import("fangz");

const root_cmd = @import("commands/root.zig");

pub fn main() !void {
    var app = try fangz.App.init(std.heap.page_allocator, .{
        .name = "typm",
        .description = "A CLI for managing Typst packages",
        .version = "0.1.0",
    });
    defer app.deinit();

    try root_cmd.register(app.root());
    try app.executeProcess();
}

fn getTypstVersion() !semver {
    const allocator = std.heap.page_allocator;

    const result = std.process.Child.run(.{
        .allocator = allocator,
        .argv = &.{ "typst", "--version" },
    }) catch {
        return error.TypstNotFound;
    };

    defer {
        allocator.free(result.stdout);
        allocator.free(result.stderr);
    }

    if (result.term.Exited != 0) {
        std.process.exit(1);
    }

    const stdout = std.mem.trim(u8, result.stdout, "\n\r\t");

    var it = std.mem.splitScalar(u8, stdout, ' ');
    _ = it.next() orelse return error.InvalidOutput;
    const version_str = it.next() orelse return error.InvalidOutput;

    return semver.parse(version_str) catch error.InvalidSemver;
}

test {
    std.testing.refAllDecls(@This());
}
