from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

URL = "http://localhost:8000/index_tv.html"
OUT_DIR = Path("export_png")
OUT_DIR.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=2  # higher resolution
    )

    page.goto(URL, wait_until="networkidle")
    page.add_style_tag(content="*{scroll-behavior:auto!important;}")

    slides = page.query_selector_all("section.slide[data-slide]")
    if not slides:
        raise RuntimeError("No slides found. Check selector or HTML structure.")

    # Sort slides by data-slide number
    def slide_num(el):
        try:
            return int(el.get_attribute("data-slide"))
        except:
            return 10**9

    slides = sorted(slides, key=slide_num)

    for i, el in enumerate(slides, start=1):
        page.evaluate("(el) => el.scrollIntoView({block:'start'})", el)
        page.wait_for_timeout(1400)  # gives Plotly iframes time to settle

        out_png = OUT_DIR / f"slide_{i:02d}.png"
        el.screenshot(path=str(out_png))
        print("Saved", out_png)

    browser.close()

# Build a single PDF from PNGs
pngs = sorted(OUT_DIR.glob("slide_*.png"))
imgs = [Image.open(p).convert("RGB") for p in pngs]
imgs[0].save("bus_delays_lux.pdf", save_all=True, append_images=imgs[1:])

print("✅ PDF saved as bus_delays_lux.pdf")
