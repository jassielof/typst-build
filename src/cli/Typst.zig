const std = @import("std");
const builtin = @import("builtin");

/// Get the cache directory of Typst.
/// Either checking the environment variable, or the default one based on the OS.
pub fn getCacheDir(allocator: std.mem.Allocator) ![]u8 {
    // const env_var = "TYPST_PACKAGE_CACHE_PATH";

    var env = std.process.getEnvMap(allocator) catch return error.EnvError;
    defer env.deinit();

    const home = try std.process.getEnvVarOwned(allocator, "HOME");

    var base: []const u8 = undefined;

    switch (builtin.os.tag) {
        .windows => {
            if (env.get("LOCALAPPDATA")) |v| {
                base = v;
            } else {
                base = try std.fs.path.join(allocator, &.{ home, "AppData", "Local" });
            }
        },
        .macos => {
            base = try std.fs.path.join(allocator, &.{ home, "Library", "Caches" });
        },
        else => { // Linux / other Unix
            if (env.get("XDG_CACHE_HOME")) |v| {
                base = v;
            } else {
                base = try std.fs.path.join(allocator, &.{ home, ".cache" });
            }
        },
    }

    return std.fs.path.join(allocator, &.{ base, "typst" });
}

test getCacheDir {
    const allocator = std.testing.allocator;
    const cache_dir = try getCacheDir(allocator);
    defer allocator.free(cache_dir);

    std.debug.print("Cache directory: {s}\n", .{cache_dir});
}
