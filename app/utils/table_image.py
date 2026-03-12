"""Построение PNG-изображения таблицы из pandas DataFrame (matplotlib)."""
from io import BytesIO
from typing import Optional

import pandas as pd

from config.settings import settings


# Максимум строк/столбцов для отображения в PNG (чтобы не перегружать картинку)
MAX_TABLE_ROWS = 50
MAX_TABLE_COLS = 12


def dataframe_to_png(df: pd.DataFrame) -> BytesIO:
    """
    Строит PNG-изображение таблицы из DataFrame.
    Размер фигуры берётся из settings (CHART_TABLE_FIG_WIDTH, CHART_TABLE_FIG_HEIGHT).
    При большом числе строк/столбцов ограничивает вывод (топ N строк) и подстраивает шрифт.
    Возвращает BytesIO с PNG (курсор в начале).
    """
    if df is None or df.empty:
        buf = BytesIO()
        return buf

    width = getattr(settings, "CHART_TABLE_FIG_WIDTH", 12.0)
    height = getattr(settings, "CHART_TABLE_FIG_HEIGHT", 8.0)

    # Ограничиваем размер для читаемости
    df = df.head(MAX_TABLE_ROWS)
    if len(df.columns) > MAX_TABLE_COLS:
        df = df.iloc[:, :MAX_TABLE_COLS]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width, height))
    ax.axis("off")

    # Преобразуем в строки для отображения (короткие числа/даты)
    cell_text = []
    for _, row in df.iterrows():
        cell_text.append([str(v)[:50] for v in row])
    col_labels = [str(c)[:30] for c in df.columns]

    nrows, ncols = len(cell_text), len(col_labels)
    font_size = max(6, min(10, 14 - nrows // 10 - ncols // 4))

    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(1.2, 1.8)

    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return buf
