import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

async function signIn(page: Page, profile = "demo-analyst") {
  await page.goto("/");
  await page.getByLabel("Choose a demonstration profile").selectOption(profile);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Close overview" }),
  ).toBeVisible();
  await expect(page.getByText("77", { exact: true }).first()).toBeVisible();
}

test("import, validate, inspect exact cent, assign and export evidence", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signIn(page);
  await page.screenshot({
    path: "../../reports/dashboard.png",
    fullPage: true,
  });
  await page.goto("/sources");
  await page
    .getByLabel("Source package")
    .setInputFiles(path.resolve("../../fixtures/gl.zip"));
  await page.getByRole("button", { name: "Import evidence" }).click();
  await expect(page.getByRole("status")).toContainText("Evidence imported");
  await page
    .getByLabel("Source package")
    .setInputFiles(path.resolve("../../fixtures/fccs.zip"));
  await page.getByRole("button", { name: "Import evidence" }).click();
  await expect(page.getByRole("status")).toContainText("Evidence imported");
  await page.goto("/runs");
  await page
    .getByRole("button", { name: "Run validation", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Validation requested");
  await page.goto("/reconciliation");
  await page.getByLabel("Search controls").fill("US100");
  await page.getByLabel("Control status").selectOption("FAIL");
  const row = page
    .getByRole("row")
    .filter({ has: page.getByRole("button", { name: "400100", exact: true }) });
  await expect(row).toContainText("100.01");
  await expect(row).toContainText("100.00");
  await expect(row).toContainText("0.01");
  await row.getByRole("button", { name: "400100", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("Source lineage");
  await expect(page.getByRole("dialog")).toContainText("US100-400100");
  await page.screenshot({
    path: "../../reports/exact-cent-evidence.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page.goto("/exceptions");
  const issue = page
    .getByRole("row")
    .filter({ hasText: "C04 Reconciliation" })
    .filter({ hasText: "US100" })
    .first();
  await issue.getByRole("button", { name: "Review", exact: true }).click();
  await page.getByLabel("Assigned owner").selectOption("demo-analyst");
  const currentState = await page.getByLabel("Review state").inputValue();
  await page.getByLabel("Review state").selectOption(currentState);
  await page
    .getByLabel("Review note")
    .fill(
      "Browser regression verified original source lines and exact-cent discrepancy.",
    );
  await page.getByRole("button", { name: "Save review" }).click();
  await expect(page.getByRole("status")).toContainText("Review recorded");
  await page.goto("/reports");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download ZIP" }).click();
  const download = await downloadPromise;
  await download.saveAs("../../reports/browser-audit-bundle.zip");
  expect(await download.failure()).toBeNull();
  expect(errors).toEqual([]);
});

test("every requested page loads real service data", async ({ page }) => {
  await signIn(page, "demo-admin");
  for (const [route, heading] of [
    ["runs", "Validation runs"],
    ["journals", "Journals"],
    ["intercompany", "Intercompany"],
    ["currency", "Currency translation"],
    ["history", "History"],
    ["policies", "Mappings & policies"],
    ["connections", "Connections"],
    ["jobs", "Automation"],
    ["administration", "Administration"],
  ]) {
    await page.goto(`/${route}`);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  }
  await expect(page.getByText("CHAIN VERIFIED")).toBeVisible();
  await page.goto("/connections");
  await page
    .getByRole("button", { name: "Test configured connection" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "No Oracle connection was attempted",
  );
});

test("mobile layout keeps controls reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.screenshot({ path: "../../reports/mobile.png", fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.goto("/reports");
  await expect(page.getByRole("link", { name: "Download ZIP" })).toBeVisible();
});

test("queued API state stays pending and refreshes after completion", async ({
  page,
}) => {
  await signIn(page);
  const response = await page.request.get("/api/runs");
  const run = (await response.json())[0];
  let polls = 0;
  await page.route(`**/api/runs/${run.id}`, async (route) => {
    const actual = await route.fetch();
    const document = await actual.json();
    polls += 1;
    await route.fulfill({
      response: actual,
      json:
        polls <= 2
          ? {
              ...document,
              state: "QUEUED",
              result: null,
              counts: {},
              completed: null,
            }
          : document,
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Validation queued", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Waiting for a worker.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Your close needs a closer look",
      exact: true,
    }),
  ).toBeVisible({ timeout: 15000 });
  expect(polls).toBeGreaterThanOrEqual(3);
});
