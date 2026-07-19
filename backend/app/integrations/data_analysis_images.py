"""表格分析单元格 — 将各类输入规范化为 matplotlib imshow 可用的数组。"""

from __future__ import annotations

import numpy as np
import pandas as pd


def prepare_image_for_imshow(image) -> np.ndarray:
    arr = _to_array(image)
    if arr.dtype == np.object_:
        arr = _coerce_object_array(arr)
    return arr


def _to_array(image) -> np.ndarray:
    try:
        from PIL import Image

        if isinstance(image, Image.Image):
            return np.asarray(image)
    except ImportError:
        pass

    if isinstance(image, (pd.DataFrame, pd.Series)):
        return image.to_numpy()

    return np.asarray(image)


def _coerce_object_array(arr: np.ndarray) -> np.ndarray:
    flat = arr.ravel()
    if flat.size == 1:
        item = flat[0]
        try:
            from PIL import Image

            if isinstance(item, Image.Image):
                return np.asarray(item)
        except ImportError:
            pass
        if hasattr(item, "__array__"):
            nested = np.asarray(item)
            if nested.dtype != np.object_:
                return nested

    try:
        numeric = pd.to_numeric(pd.Series(flat), errors="raise").to_numpy(dtype=float)
        return numeric.reshape(arr.shape)
    except (ValueError, TypeError) as exc:
        raise TypeError(
            "display_image 需要数值数组或图像，当前 dtype=object 且无法转换为数值"
        ) from exc
