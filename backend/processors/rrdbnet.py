"""RRDBNet (Real-ESRGAN) em PyTorch puro.

Motivo: o pacote `realesrgan` do PyPI ARRASTA o `gfpgan` (reconstrução facial
generativa, PROIBIDA pela política do projeto) e uma cadeia pesada de
dependências (basicsr/scipy/scikit-image). Aqui reimplementamos apenas a rede
de super-resolução de TEXTURA (RRDBNet, licença Apache-2.0 da Xinntao), usando
somente `torch`. Nenhum módulo de rosto é importado.

A arquitetura e os nomes de camadas seguem o original para carregar os pesos
oficiais `RealESRGAN_x2plus.pth` / `RealESRGAN_x4plus.pth`.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn


def pixel_unshuffle(x: torch.Tensor, scale: int) -> torch.Tensor:
    return F.pixel_unshuffle(x, scale)


def make_layer(block, num_blocks, **kwargs):
    return nn.Sequential(*[block(**kwargs) for _ in range(num_blocks)])


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32):
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat: int, num_grow_ch: int = 32):
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x):
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, num_in_ch=3, num_out_ch=3, scale=4, num_feat=64, num_block=23, num_grow_ch=32):
        super().__init__()
        self.scale = scale
        if scale == 2:
            num_in_ch = num_in_ch * 4
        self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
        self.body = make_layer(RRDB, num_block, num_feat=num_feat, num_grow_ch=num_grow_ch)
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = pixel_unshuffle(x, scale=2) if self.scale == 2 else x
        feat = self.conv_first(feat)
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


def load_rrdbnet(weights_path: str, scale: int, device: torch.device) -> RRDBNet:
    """Cria a RRDBNet e carrega os pesos oficiais (params_ema ou params)."""
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=scale)
    state = torch.load(weights_path, map_location="cpu")
    for key in ("params_ema", "params_ema_network", "params", "state_dict"):
        if isinstance(state, dict) and key in state:
            state = state[key]
            break
    # remove prefixos comuns
    cleaned = {}
    for k, v in state.items():
        name = k[7:] if k.startswith("module.") else k
        cleaned[name] = v
    model.load_state_dict(cleaned, strict=True)
    model.eval()
    model.to(device)
    return model


@torch.no_grad()
def enhance(model: RRDBNet, bgr: np.ndarray, scale: int, device: torch.device,
            tile: int = 512, tile_pad: int = 12) -> np.ndarray:
    """Super-resolução com tiling (limita memória) — apenas textura, sem rostos."""
    img = cv2_rgb_to_tensor(bgr).to(device)
    _, _, h, w = img.shape

    # pixel_unshuffle exige dimensões pares -> pad múltiplo de 4.
    pad_h = (4 - h % 4) % 4
    pad_w = (4 - w % 4) % 4
    if pad_h or pad_w:
        img = F.pad(img, (0, pad_w, 0, pad_h), mode="reflect")

    ph, pw = img.shape[2], img.shape[3]
    if max(ph, pw) <= tile:
        out = model(img)
    else:
        out = torch.zeros((1, 3, ph * scale, pw * scale), dtype=img.dtype, device=device)
        for y in range(0, ph, tile):
            for x in range(0, pw, tile):
                y2 = min(y + tile, ph)
                x2 = min(x + tile, pw)
                y0 = max(y - tile_pad, 0)
                x0 = max(x - tile_pad, 0)
                y1 = min(y2 + tile_pad, ph)
                x1 = min(x2 + tile_pad, pw)
                patch = model(img[:, :, y0:y1, x0:x1])
                cy0 = (y - y0) * scale
                cx0 = (x - x0) * scale
                cy1 = cy0 + (y2 - y) * scale
                cx1 = cx0 + (x2 - x) * scale
                out[:, :, y * scale:y2 * scale, x * scale:x2 * scale] = patch[:, :, cy0:cy1, cx0:cx1]

    out = out[:, :, : h * scale, : w * scale]
    return tensor_to_bgr(out)


# --- conversões (import local para evitar ciclo) ---
def cv2_rgb_to_tensor(bgr: np.ndarray) -> torch.Tensor:
    rgb = bgr[:, :, ::-1].astype(np.float32) / 255.0
    return torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))[None]


def tensor_to_bgr(t: torch.Tensor) -> np.ndarray:
    arr = t.clamp_(0, 1).squeeze(0).permute(1, 2, 0).cpu().numpy()
    arr = (arr * 255.0).round().astype(np.uint8)
    return np.ascontiguousarray(arr[:, :, ::-1])
