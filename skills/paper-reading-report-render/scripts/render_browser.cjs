"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const [
  htmlPath,
  pdfPath,
  metricsPath,
  browserExecutable,
  nodeModules,
] = process.argv.slice(2);

if (!htmlPath || !pdfPath || !metricsPath || !browserExecutable || !nodeModules) {
  throw new Error("render_browser.cjs received incomplete arguments");
}

const playwright = require(path.join(nodeModules, "playwright"));

(async () => {
  const browser = await playwright.chromium.launch({
    headless: true,
    executablePath: browserExecutable,
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
    });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.evaluate(async () => {
      if (document.fonts && document.fonts.ready) {
        await document.fonts.ready;
      }
    });
    await page.waitForTimeout(250);

    const metrics = await page.evaluate(() => {
      const missingImages = [...document.images]
        .filter((img) => !img.complete || img.naturalWidth === 0)
        .map((img) => img.getAttribute("src") || img.getAttribute("alt") || "unknown");
      const overflow = [...document.querySelectorAll("body *")]
        .filter((element) => element.scrollWidth > element.clientWidth + 3)
        .map((element) => ({
          tag: element.tagName,
          className: element.className || "",
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
        }))
        .filter((item) => item.tag !== "PRE" && !String(item.className).includes("table-wrap"));
      const fontSizes = [...document.querySelectorAll("p, li, td, th, figcaption, span, a")]
        .map((element) => Number.parseFloat(getComputedStyle(element).fontSize))
        .filter(Number.isFinite);
      return {
        missing_images: missingImages,
        horizontal_overflow: overflow,
        min_font_px: fontSizes.length ? Math.min(...fontSizes) : null,
        source_link_count: document.querySelectorAll('a.source[href^="#source-"]').length,
        source_row_count: document.querySelectorAll(".source-row").length,
        report_asset_count: document.querySelectorAll("[data-report-asset]").length,
        document_height_px: document.documentElement.scrollHeight,
      };
    });

    await page.emulateMedia({ media: "print" });
    await page.pdf({
      path: pdfPath,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      margin: { top: "0", right: "0", bottom: "0", left: "0" },
    });
    const pdfBytes = fs.readFileSync(pdfPath);
    const pageCount = (pdfBytes.toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length;
    metrics.pdf_page_count = pageCount;
    fs.writeFileSync(metricsPath, JSON.stringify(metrics, null, 2) + "\n", "utf8");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
