const std = @import("std");

const fangz = @import("fangz");

const info = @import("info.zig");
const update = @import("update.zig");
const uninstall = @import("uninstall.zig");
const pack = @import("pack.zig");

pub fn register(root: *fangz.Command) !void {
    root.setHelpOnEmptyArgs(true);

    try pack.register(root);
    try info.register(root);
    try update.register(root);
    try uninstall.register(root);
}
