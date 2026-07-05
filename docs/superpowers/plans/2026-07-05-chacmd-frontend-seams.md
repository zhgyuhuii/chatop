# 察元基座 3 注入 Seam Implementation Plan（ChaCMD 前端 v1 地基）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给察元基座（`packages/app`）补 §3.7 的三个 SKU 注入 seam（BrandConfig 注入 / 首页-路由扩展注入 / landing 覆盖），让新 SKU（apps/chacmd 指挥大屏）能注入自己的品牌+路由而**不改基座行为**——无 brand 注入时察元逐字节不变。

**Architecture:** 仿基座已有的 `registerToolCard` 运行时注册器模式：加一个模块级"当前 brand"注册表（`setActiveBrand`/`getActiveBrand`，Shell 启动时 set 一次）。路由解析改为"基座内置条目 + brand.routeExtensions 合并"（纯函数 `effectiveRouteEntries`）；landing 路径改为 `resolveLandingPath(brand)`。默认无 brand → 合并结果 === 内置 `ROUTE_ENTRIES`、landing === `/home`，察元行为不变。

**Tech Stack:** TypeScript / React 19 / TanStack Router / vitest（基座已有 51 个 .test.ts）。

**工作目录:** `/work/chayuan-desktop/chayuan-client`（git 仓 chayuan-desktop-own，分支 main，**工作树有大量非本任务既有改动——只路径限定 `git add packages/app/...`，绝不 `git add -A`**）。

**验证:** `cd /work/chayuan-desktop/chayuan-client && pnpm --filter @chayuan/app exec vitest run <file>`；类型检查 `pnpm --filter @chayuan/app typecheck`。前置：`pnpm install` 已完成。

---

## File Structure

### 新增
- `packages/app/src/brand/types.ts` — `BrandConfig` / `RouteExtension` 类型
- `packages/app/src/brand/registry.ts` — `setActiveBrand`/`getActiveBrand`/`resolveLandingPath`（模块级注册表）
- `packages/app/src/brand/registry.test.ts` — 注册表单测
- `packages/app/src/features/shell/routeMerge.ts` — `effectiveRouteEntries(base, brand)` 纯函数
- `packages/app/src/features/shell/routeMerge.test.ts` — 合并单测

### 修改
- `packages/app/src/features/shell/page-registry.tsx` — `resolveRoute` 改用 `effectiveRouteEntries(ROUTE_ENTRIES, getActiveBrand())`
- `packages/app/src/Shell.tsx` — `ShellEnv` 加 `brand?: BrandConfig`；Shell 启动 `setActiveBrand(env.brand)`；`createAppRouter(queryClient, env.brand)`
- `packages/app/src/router/index.tsx` — `createAppRouter(queryClient, brand?)`；`/` redirect 用 `resolveLandingPath(brand)`

---

## Task 1: BrandConfig 类型 + 品牌注册表

**Files:**
- Create: `packages/app/src/brand/types.ts`, `packages/app/src/brand/registry.ts`, `packages/app/src/brand/registry.test.ts`

- [ ] **Step 1: 写失败测试**

`packages/app/src/brand/registry.test.ts`:
```ts
import { describe, expect, it, beforeEach } from 'vitest';
import { getActiveBrand, resolveLandingPath, setActiveBrand } from './registry';

describe('brand registry', () => {
  beforeEach(() => setActiveBrand(undefined));

  it('默认无 brand', () => {
    expect(getActiveBrand()).toBeUndefined();
  });

  it('set 后可取回', () => {
    setActiveBrand({ appName: 'ChaCMD 指挥台' });
    expect(getActiveBrand()?.appName).toBe('ChaCMD 指挥台');
  });

  it('landing 默认 /home', () => {
    expect(resolveLandingPath(undefined)).toBe('/home');
    expect(resolveLandingPath({ appName: 'x' })).toBe('/home');
  });

  it('landing 可被 brand 覆盖', () => {
    expect(resolveLandingPath({ appName: 'x', landingPath: '/command' })).toBe('/command');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pnpm --filter @chayuan/app exec vitest run src/brand/registry.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现类型 + 注册表**

`packages/app/src/brand/types.ts`:
```ts
import type * as React from 'react';
import type { RouteEntry } from '../features/shell/page-registry';

/** SKU 品牌 + 路由扩展注入契约（§3.7）。无注入时基座行为不变。 */
export interface BrandConfig {
  /** 应用名（顶栏/标题）。"察元 AI" | "ChaCMD 指挥台" */
  appName: string;
  /** 该 SKU 的落地路径（landing）。缺省 /home（察元现状）。 */
  landingPath?: string;
  /** 该 SKU 追加的路由条目（不覆盖基座内置路由）。 */
  routeExtensions?: RouteEntry[];
  /** 首页组件覆盖（可选；缺省用基座 /home 的 HomePage）。 */
  homeComponent?: React.ComponentType;
}
```

`packages/app/src/brand/registry.ts`:
```ts
import type { BrandConfig } from './types';

// 模块级"当前 SKU 品牌"，Shell 启动时 set 一次（仿 registerToolCard 模式）。
let _activeBrand: BrandConfig | undefined;

export function setActiveBrand(brand: BrandConfig | undefined): void {
  _activeBrand = brand;
}

export function getActiveBrand(): BrandConfig | undefined {
  return _activeBrand;
}

export function resolveLandingPath(brand: BrandConfig | undefined): string {
  return brand?.landingPath ?? '/home';
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pnpm --filter @chayuan/app exec vitest run src/brand/registry.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop/chayuan-client
git add packages/app/src/brand/types.ts packages/app/src/brand/registry.ts packages/app/src/brand/registry.test.ts
git commit -m "feat(chacmd-seam): BrandConfig 类型 + 品牌注册表(setActiveBrand/landing)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: effectiveRouteEntries 合并（内置 + routeExtensions）

**Files:**
- Create: `packages/app/src/features/shell/routeMerge.ts`, `packages/app/src/features/shell/routeMerge.test.ts`

- [ ] **Step 1: 写失败测试**

`packages/app/src/features/shell/routeMerge.test.ts`:
```tsx
import { describe, expect, it } from 'vitest';
import type { RouteEntry } from './page-registry';
import { effectiveRouteEntries } from './routeMerge';

const base: RouteEntry[] = [
  { pattern: /^\/home$/, render: () => null, defaultTitle: 'nav.home' },
];
const ext: RouteEntry = { pattern: /^\/command$/, render: () => null, defaultTitle: 'ChaCMD' };

describe('effectiveRouteEntries', () => {
  it('无 brand → 原样返回内置条目', () => {
    expect(effectiveRouteEntries(base, undefined)).toEqual(base);
  });

  it('有 routeExtensions → 追加到末尾', () => {
    const merged = effectiveRouteEntries(base, { appName: 'x', routeExtensions: [ext] });
    expect(merged).toHaveLength(2);
    expect(merged[1].pattern.source).toBe(/^\/command$/.source);
  });

  it('brand 无 routeExtensions → 等同内置', () => {
    expect(effectiveRouteEntries(base, { appName: 'x' })).toEqual(base);
  });

  it('内置条目不被 extension 覆盖(extension 只追加)', () => {
    const merged = effectiveRouteEntries(base, { appName: 'x', routeExtensions: [ext] });
    expect(merged[0]).toBe(base[0]);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pnpm --filter @chayuan/app exec vitest run src/features/shell/routeMerge.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现**

`packages/app/src/features/shell/routeMerge.ts`:
```ts
import type { BrandConfig } from '../../brand/types';
import type { RouteEntry } from './page-registry';

/** 内置路由条目 + brand.routeExtensions（追加，不覆盖内置）。无 brand → 原样返回。 */
export function effectiveRouteEntries(
  base: ReadonlyArray<RouteEntry>,
  brand: BrandConfig | undefined,
): RouteEntry[] {
  const exts = brand?.routeExtensions ?? [];
  return [...base, ...exts];
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pnpm --filter @chayuan/app exec vitest run src/features/shell/routeMerge.test.ts`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop/chayuan-client
git add packages/app/src/features/shell/routeMerge.ts packages/app/src/features/shell/routeMerge.test.ts
git commit -m "feat(chacmd-seam): effectiveRouteEntries 合并内置+SKU 路由扩展(追加不覆盖)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: resolveRoute 走合并后的条目

**Files:**
- Modify: `packages/app/src/features/shell/page-registry.tsx`
- Test: `packages/app/src/features/shell/page-registry.test.ts`（新增）

- [ ] **Step 1: 写失败测试（brand 注入的路由能被 resolveRoute 命中；无 brand 时行为不变）**

`packages/app/src/features/shell/page-registry.test.ts`:
```tsx
import { afterEach, describe, expect, it } from 'vitest';
import { setActiveBrand } from '../../brand/registry';
import { resolveRoute } from './page-registry';

describe('resolveRoute + brand 注入', () => {
  afterEach(() => setActiveBrand(undefined));

  it('无 brand → /home 命中内置(察元不变)', () => {
    expect(resolveRoute('/home')).not.toBeNull();
    expect(resolveRoute('/command')).toBeNull();  // 未注入时无此路由
  });

  it('注入 /command 路由后可命中', () => {
    setActiveBrand({
      appName: 'ChaCMD',
      routeExtensions: [{ pattern: /^\/command$/, render: () => null, defaultTitle: 'ChaCMD' }],
    });
    expect(resolveRoute('/command')).not.toBeNull();
    expect(resolveRoute('/home')).not.toBeNull();  // 内置仍在
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pnpm --filter @chayuan/app exec vitest run src/features/shell/page-registry.test.ts`
Expected: FAIL（resolveRoute 未走合并，`/command` 返回 null）

- [ ] **Step 3: 改 resolveRoute 用合并条目**

`packages/app/src/features/shell/page-registry.tsx`：文件顶部 import 加：
```tsx
import { getActiveBrand } from '../../brand/registry';
import { effectiveRouteEntries } from './routeMerge';
```
把 `resolveRoute` 的循环从遍历 `ROUTE_ENTRIES` 改为遍历合并结果：
```tsx
export function resolveRoute(path: string): { entry: RouteEntry; params: RouteParams } | null {
  const pathname = path.split(/[?#]/, 1)[0] || path;
  for (const entry of effectiveRouteEntries(ROUTE_ENTRIES, getActiveBrand())) {
    const m = entry.pattern.exec(pathname);
    if (m) {
      const params: RouteParams = { ...(m.groups ?? {}) };
      return { entry, params };
    }
  }
  return null;
}
```

- [ ] **Step 4: 跑测试确认通过 + 相邻回归**

Run:
```bash
pnpm --filter @chayuan/app exec vitest run src/features/shell/page-registry.test.ts src/brand src/features/shell/routeMerge.test.ts
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop/chayuan-client
git add packages/app/src/features/shell/page-registry.tsx packages/app/src/features/shell/page-registry.test.ts
git commit -m "feat(chacmd-seam): resolveRoute 走 brand 合并条目(注入路由可命中, 无 brand 不变)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: ShellEnv.brand + Shell/router 接线

**Files:**
- Modify: `packages/app/src/Shell.tsx`, `packages/app/src/router/index.tsx`

- [ ] **Step 1: ShellEnv 加 brand 字段 + Shell 启动 setActiveBrand**

`packages/app/src/Shell.tsx`：
- import 加：`import { setActiveBrand } from './brand/registry';` 和 `import type { BrandConfig } from './brand/types';`
- `ShellEnv` 接口加字段：
```ts
  /** SKU 品牌 + 路由扩展注入（§3.7）。缺省 undefined = 察元现状。 */
  brand?: BrandConfig;
```
- `Shell` 组件体开头（`routerRef` 之前）加：
```tsx
  // SKU 品牌注册一次（模块级，供 resolveRoute/landing 读取）
  if (getActiveBrand() !== env.brand) setActiveBrand(env.brand);
```
  并把 import 补上 `getActiveBrand`：`import { getActiveBrand, setActiveBrand } from './brand/registry';`
- `createAppRouter(queryClient)` 改为 `createAppRouter(queryClient, env.brand)`。

- [ ] **Step 2: createAppRouter 接受 brand，landing 用 resolveLandingPath**

`packages/app/src/router/index.tsx`：
- import 加：`import { resolveLandingPath } from '../brand/registry';` 和 `import type { BrandConfig } from '../brand/types';`
- `createAppRouter` 签名加参数（定位其函数定义处）：
```ts
export function createAppRouter(queryClient: QueryClient, brand?: BrandConfig) {
```
- 找到根 `/` 的 redirect（`redirect → /home`）处，把目标改为 `resolveLandingPath(brand)`：
```ts
    beforeLoad: () => {
      throw redirect({ to: resolveLandingPath(brand) });
    },
```
  （若原实现是常量 `'/home'`，替换为 `resolveLandingPath(brand)`；保持其余不变。）

- [ ] **Step 3: 类型检查（无独立单测，靠 tsc + 后续回归）**

Run: `pnpm --filter @chayuan/app typecheck`
Expected: 通过（无类型错误）

- [ ] **Step 4: 提交**

```bash
cd /work/chayuan-desktop/chayuan-client
git add packages/app/src/Shell.tsx packages/app/src/router/index.tsx
git commit -m "feat(chacmd-seam): ShellEnv.brand 注入 + createAppRouter landing 覆盖(§3.7)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 察元默认不变回归 + 全量校验

**Files:**
- Test: 无新增；跑全量

- [ ] **Step 1: 察元默认行为回归（无 brand → landing=/home、resolveRoute 内置齐全）**

已由 Task1/3 的"无 brand"用例覆盖。补一条集成断言到 `registry.test.ts`：
```ts
  it('无 brand 时 landing 与察元现状一致', () => {
    expect(resolveLandingPath(getActiveBrand())).toBe('/home');
  });
```
Run: `pnpm --filter @chayuan/app exec vitest run src/brand/registry.test.ts`
Expected: PASS

- [ ] **Step 2: 基座全量单测 + 类型检查（确保未破坏察元）**

Run:
```bash
cd /work/chayuan-desktop/chayuan-client
pnpm --filter @chayuan/app exec vitest run 2>&1 | tail -5
pnpm --filter @chayuan/app typecheck 2>&1 | tail -5
```
Expected: 全部通过（原 51 测试 + 本计划新增，无回归）

- [ ] **Step 3: 提交**

```bash
cd /work/chayuan-desktop/chayuan-client
git add packages/app/src/brand/registry.test.ts
git commit -m "test(chacmd-seam): 察元默认不变回归 + 全量基座测试绿

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec 覆盖（§3.7 三注入 seam）：**
- ① 品牌注入 BrandConfig（经 ShellEnv） → Task 1 + Task 4 ✓
- ② 首页/路由注入（routeExtensions 追加，不覆盖察元路由树） → Task 2 + Task 3 ✓
- ③ landing 覆盖（ChaCMD 指 /command，察元仍 /home） → Task 1(resolveLandingPath) + Task 4(createAppRouter) ✓
- 硬约束"察元逐字节不变"（无 brand 时） → Task 1/2/3/5 的"无 brand"用例 ✓

**Placeholder 扫描：** 无 TODO；每步含实际代码/命令。

**类型一致性：** `BrandConfig`（Task1）↔ effectiveRouteEntries/ShellEnv/createAppRouter 参数一致；`RouteEntry` 复用 page-registry 现有导出；`setActiveBrand/getActiveBrand/resolveLandingPath`（Task1）↔ page-registry/Shell/router 用法一致；`effectiveRouteEntries(base, brand)`（Task2）↔ resolveRoute 调用一致。

**注：② 的 homeComponent 覆盖**本计划未实现（仅 routeExtensions + landing 覆盖，足够 ChaCMD 走 /command 大屏为主页）。homeComponent 覆盖若后续需要（替换 /home 本身）另开小任务。

**不在本计划（下一个计划）：** apps/chacmd Tauri SKU 壳 + packages/chacmd-features + 3D 星群 L0 大屏（消费 /api/v1/stream）。

---

## Execution Handoff

计划保存于 `docs/superpowers/plans/2026-07-05-chacmd-frontend-seams.md`（chatop 仓）。
