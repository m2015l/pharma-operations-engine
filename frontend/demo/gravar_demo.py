"""Grava o vídeo de demonstração do frontend em MODO_DEMO (nenhuma chamada paga).

Pré-requisitos, cada um num terminal (da raiz do projeto):
    MODO_DEMO=1 uv run --with-requirements api/requirements.txt python -m uvicorn main:app --app-dir api --port 8000
    cd frontend && npm run dev

Depois:
    uv run --with playwright python frontend/demo/gravar_demo.py
    (converte para .mp4 sozinho se houver ffmpeg no PATH)

O navegador do Playwright não desenha o ponteiro do mouse no vídeo; um cursor
falso (injetado abaixo) mostra onde cada clique acontece.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

BASE = "http://localhost:3000"
PASTA = Path(__file__).resolve().parent
LARGURA, ALTURA = 1440, 900

CURSOR_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;' +
    'border-radius:50%;background:rgba(68,161,140,.35);border:2px solid #124443;' +
    'pointer-events:none;z-index:2147483647;transition:transform .12s';
  document.body.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => c.style.transform = 'scale(.7)', true);
  document.addEventListener('mouseup', () => c.style.transform = 'scale(1)', true);
});
"""

# PDF mínimo gerado aqui mesmo — a demo de envio não usa documento de cliente.
PDF_EXEMPLO = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def mover_e_clicar(page: Page, alvo: Locator, pausa_ms: int = 350) -> None:
    alvo.scroll_into_view_if_needed()
    caixa = alvo.bounding_box()
    assert caixa, "elemento sem posição na tela"
    page.mouse.move(caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2, steps=25)
    page.wait_for_timeout(pausa_ms)
    alvo.click()


def perguntar(page: Page, texto: str, n_respostas_esperadas: int) -> None:
    campo = page.get_by_role("textbox", name="Pergunta")
    mover_e_clicar(page, campo, 200)
    campo.press_sequentially(texto, delay=38)
    page.wait_for_timeout(400)
    campo.press("Enter")
    page.wait_for_function(
        "n => document.querySelectorAll('article .resposta').length >= n", arg=n_respostas_esperadas, timeout=30_000
    )
    page.wait_for_timeout(900)


def main() -> None:
    PASTA.mkdir(exist_ok=True)
    tmp_video = Path(tempfile.mkdtemp())
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(
            viewport={"width": LARGURA, "height": ALTURA},
            record_video_dir=str(tmp_video),
            record_video_size={"width": LARGURA, "height": ALTURA},
            locale="pt-BR",
        )
        contexto.add_init_script(CURSOR_JS)
        page = contexto.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        page.mouse.move(700, 450)
        page.wait_for_timeout(2500)

        # 1. Pergunta aberta: resposta com marcadores e painel de fontes.
        perguntar(page, "A gente já fez alguma obra de implantação de laboratório?", 1)
        page.wait_for_timeout(2500)
        mover_e_clicar(page, page.get_by_role("button", name="Fonte 3").first)
        page.wait_for_timeout(2200)
        mover_e_clicar(page, page.get_by_role("button", name="Fonte 5").last)
        page.wait_for_timeout(2000)

        # "Ver a fonte" do trecho [5]: abre o PDF na página citada.
        cartao5 = page.locator("aside ol > li").nth(4)  # fontes em ordem: [1]..[5]
        mover_e_clicar(page, cartao5.get_by_role("button", name="Ver a fonte"))
        page.wait_for_selector("canvas", state="visible", timeout=30_000)
        page.wait_for_function("document.querySelector('canvas.opacity-100') !== null", timeout=30_000)
        page.wait_for_timeout(3500)
        mover_e_clicar(page, page.get_by_role("button", name="Próxima página"))
        page.wait_for_timeout(2500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)

        # 2. Acompanhamento com pronome: o histórico resolve "disso".
        perguntar(page, "E o valor disso?", 2)
        page.wait_for_timeout(2000)
        mover_e_clicar(page, page.locator("article").nth(1).get_by_role("button", name="Fonte 1").first)
        page.wait_for_timeout(2500)

        # 3. Outro documento + outro pronome.
        perguntar(page, "Temos algum atestado de vapor puro ou de água purificada?", 3)
        page.wait_for_timeout(3500)
        perguntar(page, "E o valor total do contrato desse atestado?", 4)
        page.wait_for_timeout(3000)

        # 4. Acervo.
        mover_e_clicar(page, page.get_by_role("link", name="Acervo"))
        page.wait_for_selector("text=Documentos indexados")
        page.wait_for_timeout(3500)

        # 5. Enviar documento.
        mover_e_clicar(page, page.get_by_role("link", name="Enviar documento").first)
        page.wait_for_selector("text=Novo documento para o acervo")
        page.wait_for_timeout(1500)
        # No modo demo o envio é simulado (a tela avisa); nada é guardado nem indexado.
        pdf = tmp_video / "atestado-exemplo.pdf"
        pdf.write_bytes(PDF_EXEMPLO)
        page.locator("input[type=file]").set_input_files(str(pdf))
        page.wait_for_timeout(1200)
        orgao = page.get_by_label("Órgão contratante")
        mover_e_clicar(page, orgao, 200)
        orgao.press_sequentially("Instituto BioPharma de Pesquisa", delay=35)
        page.wait_for_timeout(600)
        mover_e_clicar(page, page.get_by_role("button", name="Enviar documento"))
        page.wait_for_selector("text=recebido", timeout=15_000)
        page.wait_for_timeout(4000)

        video = page.video
        contexto.close()
        navegador.close()
        bruto = Path(video.path())

    destino = PASTA / "demo.webm"
    shutil.move(bruto, destino)
    print(f"vídeo: {destino}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4 = PASTA / "demo.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(destino), "-c:v", "libx264", "-preset", "slow",
             "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
            check=True,
        )
        print(f"mp4:   {mp4}")


if __name__ == "__main__":
    main()
