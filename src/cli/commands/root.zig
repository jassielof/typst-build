const std = @import("std");
const fangz = @import("fangz");
const info = @import("info.zig");

pub fn register(root: *fangz.Command) !void {
    root.setHelpOnEmptyArgs(true);

    try info.register(root);
}
