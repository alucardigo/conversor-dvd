"""Gera packaging/icone.ico (disco azul). Rodar uma vez: python packaging/gerar_icone.py"""
from pathlib import Path

from PIL import Image, ImageDraw


def desenhar(tamanho: int) -> Image.Image:
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margem = tamanho // 16
    d.ellipse([margem, margem, tamanho - margem, tamanho - margem], fill=(26, 96, 178, 255))
    centro, furo = tamanho / 2, tamanho * 0.2
    d.ellipse([centro - furo, centro - furo, centro + furo, centro + furo], fill=(236, 243, 252, 255))
    buraco = tamanho * 0.06
    d.ellipse([centro - buraco, centro - buraco, centro + buraco, centro + buraco], fill=(26, 96, 178, 255))
    return img


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent / "icone.ico"
    desenhar(256).save(destino, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    print(destino)
