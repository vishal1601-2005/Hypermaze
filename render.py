import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import hyperbolic_maze as hm


def render(branching=4, max_depth=6, edge_length=1.1, out="maze.png",
           highlight_path_node_id=None):
    root, nodes = hm.generate_full_tree(branching=branching, max_depth=max_depth,
                                         edge_length=edge_length)

    fig, ax = plt.subplots(figsize=(9, 9))
    boundary = plt.Circle((0, 0), 1, fill=False, color="#333333", linewidth=1.5)
    ax.add_patch(boundary)

    # draw edges as true geodesics
    for n in nodes:
        for c in n.children:
            arc = hm.geodesic_arc_points(n.pos, c.pos, n=30)
            depth_frac = c.depth / max_depth
            color = plt.cm.viridis(1 - depth_frac)
            ax.plot(arc.real, arc.imag, color=color, linewidth=max(0.4, 1.6 - depth_frac), alpha=0.85)

    # draw nodes
    xs = [n.pos.real for n in nodes]
    ys = [n.pos.imag for n in nodes]
    depths = np.array([n.depth for n in nodes])
    sizes = np.maximum(2, 22 - 3 * depths)
    ax.scatter(xs, ys, c=depths, cmap="viridis_r", s=sizes, zorder=5, edgecolors="none")

    ax.scatter([0], [0], c="red", s=90, zorder=6, marker="*", label="entry point")

    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Hyperbolic maze: branching={branching}, depth={max_depth}\n"
                 f"nodes={len(nodes)} (grows as k(k-1)^(d-1))", fontsize=11)
    ax.legend(loc="lower right", frameon=False)

    plt.tight_layout()
    plt.savefig(out, dpi=160)
    plt.close()
    return len(nodes)


if __name__ == "__main__":
    n = render(branching=4, max_depth=7, edge_length=1.05, out="maze.png")
    print("rendered nodes:", n)
