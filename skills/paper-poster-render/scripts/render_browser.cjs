"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const [
  htmlPath,
  pngPath,
  pdfPath,
  metricsPath,
  widthText,
  heightText,
  pdfWidth,
  pdfHeight,
  browserExecutable,
  nodeModules,
] = process.argv.slice(2);

if (!htmlPath || !pngPath || !pdfPath || !metricsPath) {
  throw new Error("render_browser.cjs received incomplete arguments");
}

const playwright = require(path.join(nodeModules, "playwright"));
const width = Number(widthText);
const height = Number(heightText);

(async () => {
  const browser = await playwright.chromium.launch({
    headless: true,
    executablePath: browserExecutable,
  });
  try {
    const page = await browser.newPage({
      viewport: { width, height },
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

      const overflowElements = [...document.querySelectorAll("[data-panel], figure, .panel-body")]
        .filter((element) => (
          element.scrollWidth > element.clientWidth + 2 ||
          element.scrollHeight > element.clientHeight + 2
        ))
        .map((element) => ({
          panel: (
            element.getAttribute("data-panel") ||
            element.closest("[data-panel]")?.getAttribute("data-panel") ||
            null
          ),
          className: element.className,
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          clientHeight: element.clientHeight,
          scrollHeight: element.scrollHeight,
        }));

      const panels = [...document.querySelectorAll("[data-panel]")].map((element) => {
        const box = element.getBoundingClientRect();
        return {
          id: element.getAttribute("data-panel"),
          left: box.left,
          top: box.top,
          right: box.right,
          bottom: box.bottom,
        };
      });
      const overlapPairs = [];
      for (let i = 0; i < panels.length; i += 1) {
        for (let j = i + 1; j < panels.length; j += 1) {
          const a = panels[i];
          const b = panels[j];
          const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
          const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
          if (overlapX > 2 && overlapY > 2) {
            overlapPairs.push([a.id, b.id]);
          }
        }
      }
      const fontSizes = [...document.querySelectorAll("p, li, figcaption, span")]
        .map((element) => Number.parseFloat(getComputedStyle(element).fontSize))
        .filter(Number.isFinite);
      const methodAssets = [...document.querySelectorAll("[data-method-asset-id]")]
        .map((element) => element.getAttribute("data-method-asset-id"));
      const methodModules = [...document.querySelectorAll("[data-module-id]")]
        .map((element) => element.getAttribute("data-module-id"));
      const methodFallbackCards = [
        ...document.querySelectorAll('[data-method-card-mode="mechanism_flow"]'),
      ];
      const methodOriginalCards = [
        ...document.querySelectorAll('[data-method-card-mode="original_figure"]'),
      ];
      const methodOverview = document.querySelector("[data-method-overview-mode]");
      const methodOverviewStages = [
        ...document.querySelectorAll(".method-overview-stage"),
      ];
      const emptyMethodFallbackCards = methodFallbackCards
        .filter((element) => !element.querySelector(".method-flow-stage span")?.textContent?.trim())
        .map((element) => element.getAttribute("data-module-id") || "unknown");
      const keyIdea = document.querySelector("[data-key-idea-type]");
      const keyIdeaVisual = document.querySelector("[data-key-idea-visual]");
      const keyIdeaItems = [
        ...document.querySelectorAll(".key-idea-item"),
      ];
      const keyIdeaEquation = document.querySelector("[data-key-equation-id]");
      const keyIdeaImages = [...document.querySelectorAll(".key-idea-equation img")];
      const resultRoot = document.querySelector("[data-results-layout]");
      const resultAssets = [...document.querySelectorAll("[data-result-asset-id]")];
      const resultImages = [...document.querySelectorAll(".result-asset img")];
      const resultFocusTables = [
        ...document.querySelectorAll(".result-focus-table"),
      ];
      return {
        missing_images: missingImages,
        overflow_elements: overflowElements,
        overlap_pairs: overlapPairs,
        min_font_px: fontSizes.length ? Math.min(...fontSizes) : null,
        panel_count: panels.length,
        method_asset_ids: methodAssets,
        method_module_count: methodModules.length,
        method_original_card_count: methodOriginalCards.length,
        method_fallback_card_count: methodFallbackCards.length,
        method_empty_fallback_cards: emptyMethodFallbackCards,
        method_overview_mode: methodOverview
          ?.getAttribute("data-method-overview-mode") || null,
        method_overview_flow_count: methodOverviewStages.length,
        method_overview_empty: (
          methodOverview?.getAttribute("data-method-overview-empty") === "true"
          || (
            methodOverview?.getAttribute("data-method-overview-mode")
              === "sourced_method_flow"
            && methodOverviewStages.length === 0
          )
        ),
        method_visual_mode: document.querySelector("[data-method-mode]")
          ?.getAttribute("data-method-mode") || null,
        key_idea_type: keyIdea?.getAttribute("data-key-idea-type") || null,
        key_idea_inferred: keyIdea?.getAttribute("data-key-idea-inferred") || null,
        key_idea_visual_type: keyIdeaVisual?.getAttribute("data-key-idea-visual") || null,
        key_idea_visual_items: keyIdeaItems.length,
        key_idea_visual_fill_ratio: (() => {
          if (!keyIdeaVisual || !keyIdeaItems.length) {
            return 0;
          }
          const visualBox = keyIdeaVisual.getBoundingClientRect();
          const visualArea = visualBox.width * visualBox.height;
          if (visualArea <= 0) {
            return 0;
          }
          const itemArea = keyIdeaItems.reduce((total, item) => {
            const box = item.getBoundingClientRect();
            const width = Math.max(
              0,
              Math.min(box.right, visualBox.right)
                - Math.max(box.left, visualBox.left)
            );
            const height = Math.max(
              0,
              Math.min(box.bottom, visualBox.bottom)
                - Math.max(box.top, visualBox.top)
            );
            return total + width * height;
          }, 0);
          return Math.min(1, itemArea / visualArea);
        })(),
        key_idea_equation_id: keyIdeaEquation?.getAttribute("data-key-equation-id") || null,
        key_idea_equation_display_mode: keyIdeaEquation
          ?.getAttribute("data-equation-display-mode") || "none",
        key_idea_equation_object_fit: keyIdeaImages.length
          ? getComputedStyle(keyIdeaImages[0]).objectFit
          : null,
        experimental_results_layout: resultRoot
          ?.getAttribute("data-results-layout") || null,
        experimental_results_metric_count: document.querySelectorAll(
          ".result-metric-card"
        ).length,
        experimental_results_assets: resultAssets.map((element) => ({
          id: element.getAttribute("data-result-asset-id"),
          role: element.getAttribute("data-result-asset-role"),
          type: element.getAttribute("data-result-asset-type"),
        })),
        experimental_results_images: resultImages.map((img) => {
          const box = img.getBoundingClientRect();
          const contentScale = Math.min(
            box.width / Math.max(1, img.naturalWidth),
            box.height / Math.max(1, img.naturalHeight),
          );
          return {
            id: img.closest("[data-result-asset-id]")
              ?.getAttribute("data-result-asset-id") || null,
            role: img.closest("[data-result-asset-role]")
              ?.getAttribute("data-result-asset-role") || null,
            object_fit: getComputedStyle(img).objectFit,
            rendered_width: box.width,
            rendered_height: box.height,
            natural_width: img.naturalWidth,
            natural_height: img.naturalHeight,
            content_scale: contentScale,
            source_pixels_per_display_pixel:
              contentScale > 0 ? 1 / contentScale : null,
          };
        }),
        experimental_results_focus_tables: resultFocusTables.map((table) => {
          const box = table.getBoundingClientRect();
          const wrap = table.closest(".result-focus-table-wrap");
          const cells = [...table.querySelectorAll("th, td")];
          const fontSizes = cells.map((cell) =>
            parseFloat(getComputedStyle(cell).fontSize),
          );
          return {
            id: table.closest("[data-result-asset-id]")
              ?.getAttribute("data-result-asset-id") || null,
            rendered_width: box.width,
            rendered_height: box.height,
            available_width: wrap?.clientWidth || box.width,
            scroll_width: Math.max(table.scrollWidth, wrap?.scrollWidth || 0),
            horizontal_overflow:
              Math.max(table.scrollWidth, wrap?.scrollWidth || 0) >
              (wrap?.clientWidth || box.width) + 1,
            minimum_font_px: fontSizes.length
              ? Math.min(...fontSizes)
              : null,
            rows: table.querySelectorAll("tbody tr").length,
            columns: table.querySelectorAll("thead th").length,
          };
        }),
      };
    });

    await page.screenshot({ path: pngPath, fullPage: true });
    await page.emulateMedia({ media: "print" });
    await page.pdf({
      path: pdfPath,
      width: pdfWidth,
      height: pdfHeight,
      printBackground: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
      preferCSSPageSize: false,
    });
    fs.writeFileSync(metricsPath, JSON.stringify(metrics, null, 2) + "\n", "utf8");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
