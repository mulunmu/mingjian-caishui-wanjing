"""报告图表：matplotlib 预渲染 PNG，供 FPDF 嵌入。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_CJK_CONFIGURED = False


def _configure_cjk_font() -> None:
    global _CJK_CONFIGURED
    if _CJK_CONFIGURED:
        return
    try:
        import matplotlib
        from matplotlib import font_manager

        candidates = [
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
        ]
        for path in candidates:
            if not path.exists():
                continue
            font_manager.fontManager.addfont(str(path))
            name = font_manager.FontProperties(fname=str(path)).get_name()
            matplotlib.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            _CJK_CONFIGURED = True
            return
    except Exception:
        pass


def _bar_colors(n: int) -> list[str]:
    palette = ["#2563eb", "#0891b2", "#059669", "#d97706", "#dc2626", "#64748b"]
    return [palette[i % len(palette)] for i in range(n)]


def _fmt_title(title: str = "", subtitle: str = "") -> str | None:
    """图表标题 + 副标题（分母/口径说明），副标题换行附于标题下方。"""
    if title and subtitle:
        return f"{title}\n{subtitle}"
    return title or subtitle or None


def render_bar_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """将 judgment charts 结构渲染为 PNG。失败时返回 False（报告仍可无图输出）。"""
    if chart.get("type") != "bar":
        return False
    data = chart.get("data") or {}
    labels = data.get("labels") or []
    series = data.get("series") or []
    if not labels or not series:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _configure_cjk_font()
    except ImportError:
        return False

    values = series[0].get("values") or []
    if len(values) != len(labels):
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(labels)
    horizontal = chart.get("orientation") == "horizontal" or n > 10
    if horizontal:
        fig_h = max(3.6, 0.32 * n + 1.2)
        fig, ax = plt.subplots(figsize=(7.2, fig_h), dpi=120)
        y = range(n)
        width = 0.7 / max(len(series), 1)
        for si, s in enumerate(series):
            vals = s.get("values") or []
            if len(vals) != len(labels):
                return False
            offset = (si - (len(series) - 1) / 2) * width
            positions = [yi + offset for yi in y]
            ax.barh(
                positions,
                vals,
                height=width * 0.92,
                label=s.get("name") or f"序列{si + 1}",
                color=_bar_colors(len(series))[si % 6],
            )
        ax.set_yticks(list(y))
        ax.set_yticklabels(labels, fontsize=8 if n > 14 else 9)
        ax.invert_yaxis()
        xlabel = series[0].get("name") or "数值" if len(series) == 1 else "数值"
        ax.set_xlabel(xlabel, fontsize=10)
        if len(series) > 1:
            ax.legend(fontsize=9, loc="lower right")
        ax.grid(axis="x", linestyle="--", alpha=0.35)
    else:
        fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=120)
        x = range(n)
        width = 0.8 / max(len(series), 1)
        for si, s in enumerate(series):
            vals = s.get("values") or []
            if len(vals) != len(labels):
                return False
            offset = (si - (len(series) - 1) / 2) * width
            positions = [xi + offset for xi in x]
            ax.bar(
                positions,
                vals,
                width=width * 0.92,
                label=s.get("name") or f"序列{si + 1}",
                color=_bar_colors(len(series))[si % 6],
            )
        ax.set_xticks(list(x))
        rot = 45 if n > 8 else (18 if n > 5 else 0)
        fontsize = 8 if n > 10 else 10
        ax.set_xticklabels(labels, fontsize=fontsize, rotation=rot, ha="right" if rot else "center")
        ylabel = series[0].get("name") or "数值" if len(series) == 1 else "数值"
        ax.set_ylabel(ylabel, fontsize=10)
        if len(series) > 1:
            ax.legend(fontsize=9, loc="upper right")
        ax.grid(axis="y", linestyle="--", alpha=0.35)
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_line_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """趋势折线图（line）。"""
    if chart.get("type") != "line":
        return False
    data = chart.get("data") or {}
    labels = data.get("labels") or []
    series = data.get("series") or []
    if not labels or not series:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _configure_cjk_font()
    except ImportError:
        return False

    values = series[0].get("values") or []
    if len(values) != len(labels):
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=120)
    x = range(len(labels))
    palette = ["#2563eb", "#059669", "#d97706", "#dc2626"]
    for si, s in enumerate(series):
        vals = s.get("values") or []
        if len(vals) != len(labels):
            return False
        color = palette[si % len(palette)]
        ax.plot(x, vals, marker="o", color=color, linewidth=2.2, markersize=5, label=s.get("name") or f"序列{si + 1}")
        if len(series) == 1:
            ax.fill_between(x, vals, alpha=0.12, color=color)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=10, rotation=18 if len(labels) > 5 else 0, ha="right")
    ax.set_ylabel(series[0].get("name") or "数值", fontsize=10)
    ax.axhline(0, color="#cbd5e1", linewidth=0.8)
    if len(series) > 1:
        ax.legend(fontsize=9, loc="best")
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_pie_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """占比饼图（pie），过滤 0 值扇区。"""
    if chart.get("type") != "pie":
        return False
    data = chart.get("data") or {}
    labels = data.get("labels") or []
    series = data.get("series") or []
    if not labels or not series:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _configure_cjk_font()
    except ImportError:
        return False

    values = series[0].get("values") or []
    if len(values) != len(labels):
        return False
    pairs = [(l, v) for l, v in zip(labels, values) if v]
    if not pairs:
        return False
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 3.4), dpi=120)
    colors = _bar_colors(len(labels))
    ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        textprops={"fontsize": 10},
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=8)
    ax.axis("equal")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_dimension_attribution_png(attribution: dict[str, Any], output_path: Path) -> bool:
    """六维经营表现水平条形图（稳健/中等/偏弱，业务语言）。"""
    dims = attribution.get("dimensions") or {}
    if not dims:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _configure_cjk_font()
    except ImportError:
        return False

    from app.services.assessment_weights import DIMENSION_WEIGHTS
    from app.services.report_templates import business_level

    _LEVEL_ORDER = {"偏弱": 1, "中等": 2, "稳健": 3}

    labels: list[str] = []
    values: list[int] = []
    for key in DIMENSION_WEIGHTS:
        d = dims.get(key)
        if not d:
            continue
        lvl = business_level(float(d.get("score") or 0))
        labels.append(d.get("label") or key)
        values.append(_LEVEL_ORDER.get(lvl, 2))

    if not labels:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 3.0), dpi=120)
    y_pos = range(len(labels))
    colors = ["#dc2626" if v == 1 else "#f59e0b" if v == 2 else "#2563eb" for v in values]
    ax.barh(list(y_pos), values, color=colors, height=0.55)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["偏弱", "中等", "稳健"], fontsize=10)
    ax.set_title("六维经营表现", fontsize=12, pad=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_radar_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """六维雷达图（radar）。"""
    if chart.get("type") != "radar":
        return False
    data = chart.get("data") or {}
    indicators = data.get("indicators") or []
    values = data.get("values") or []
    if not indicators or len(values) != len(indicators):
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        _configure_cjk_font()
    except ImportError:
        return False

    labels = [i.get("name") or "" for i in indicators]
    max_val = max(float(i.get("max") or 100) for i in indicators)
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    vals = [float(v) for v in values]
    vals_closed = vals + vals[:1]
    angles_closed = angles + angles[:1]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=120, subplot_kw={"polar": True})
    ax.plot(angles_closed, vals_closed, color="#2563eb", linewidth=2.2)
    ax.fill(angles_closed, vals_closed, color="#2563eb", alpha=0.18)
    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, max_val)
    ax.set_yticks([max_val * 0.25, max_val * 0.5, max_val * 0.75, max_val])
    ax.grid(color="#cbd5e1", linestyle="--", alpha=0.6)
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=16)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_heatmap_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """行业×信号热力图（heatmap）。"""
    if chart.get("type") != "heatmap":
        return False
    data = chart.get("data") or {}
    x_labels = data.get("x_labels") or []
    y_labels = data.get("y_labels") or []
    cells = data.get("values") or []
    if not x_labels or not y_labels or not cells:
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        _configure_cjk_font()
    except ImportError:
        return False

    matrix = np.zeros((len(y_labels), len(x_labels)))
    for cell in cells:
        if len(cell) < 3:
            continue
        xi, yi, val = int(cell[0]), int(cell[1]), float(cell[2])
        if 0 <= yi < len(y_labels) and 0 <= xi < len(x_labels):
            matrix[yi, xi] = val

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, max(3.0, len(y_labels) * 0.45 + 1.5)), dpi=120)
    # 「Blues」单色序（仅蓝色、明度渐变）：对所有常见色觉缺陷（红/绿/蓝盲）均可区分。
    vmax = float(matrix.max()) if matrix.size else 0.0
    if vmax <= 0:
        vmax = 1.0
    cmap = plt.get_cmap("Blues")
    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
    ax.set_xticks(range(len(x_labels)))
    ax.set_xticklabels(x_labels, fontsize=9, rotation=18, ha="right")
    ax.set_yticks(range(len(y_labels)))
    ax.set_yticklabels(y_labels, fontsize=10)
    for yi in range(len(y_labels)):
        for xi in range(len(x_labels)):
            val = matrix[yi, xi]
            if val:
                rgba = cmap(float(val) / vmax)
                lum = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                text_color = "#ffffff" if lum < 0.5 else "#0f172a"
                ax.text(xi, yi, int(val), ha="center", va="center", color=text_color, fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=8)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()


def render_funnel_chart_png(chart: dict[str, Any], output_path: Path, *, title: str = "", subtitle: str = "") -> bool:
    """风险筛查漏斗图（funnel）。"""
    if chart.get("type") != "funnel":
        return False
    data = chart.get("data") or {}
    labels = data.get("labels") or []
    values = data.get("values") or []
    if not labels or len(values) != len(labels):
        return False

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _configure_cjk_font()
    except ImportError:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.8, max(3.2, len(labels) * 0.55 + 1.2)), dpi=120)
    y_pos = list(range(len(labels)))
    colors = ["#2563eb", "#0891b2", "#059669", "#d97706"][: len(labels)]
    bars = ax.barh(y_pos, values, color=colors, height=0.55)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.invert_yaxis()
    max_val = max(values) or 1
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max_val * 0.02,
            bar.get_y() + bar.get_height() / 2,
            str(int(val)),
            va="center",
            fontsize=10,
        )
    ax.set_xlabel("主体数", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.35)
    t = _fmt_title(title, subtitle)
    if t:
        ax.set_title(t, fontsize=12, pad=8)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path.exists()
