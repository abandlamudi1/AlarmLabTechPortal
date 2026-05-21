# FW Testing Platform - Design System

Comprehensive design system documentation for the FW Testing Platform, establishing consistent patterns and best practices across the application.

## Overview

This design system provides guidance on:
- **Foundations**: Core design primitives (colors, typography, spacing, shadows)
- **Components**: Reusable UI components with usage guidelines
- **Patterns**: Common UI patterns and page templates
- **Accessibility**: WCAG 2.1 AA compliance standards

## 🎨 Using Storybook

**Storybook is your interactive component playground** — the fastest way to explore, test, and develop UI components in isolation.

### Quick Start

```bash
# Start Storybook (runs on port 6006)
cd frontend
npm run storybook

# View in browser
open http://localhost:6006
```

### Why Use Storybook?

✅ **Visual Component Library** - See all components, variants, and states in one place
✅ **Interactive Development** - Modify props in real-time, test different states
✅ **Design QA** - Review dark/light mode, responsive behavior, accessibility
✅ **Documentation** - Auto-generated props tables and usage examples
✅ **Consistency Check** - Ensure components follow design system patterns

### Daily Workflow

**Before creating a new component:**
1. Check Storybook for existing patterns
2. Reuse or extend existing components when possible
3. Only create new components when existing ones don't meet the need

**When modifying a component:**
1. Update the component code
2. Update its `.stories.tsx` file to reflect changes
3. Test all variants in Storybook (light/dark, all states)
4. Use Storybook for visual QA before creating PR

**When reviewing PRs:**
1. Run Storybook locally to see component changes
2. Check all stories pass and render correctly
3. Verify accessibility (use a11y addon in Storybook)

### Creating New Stories

Use the auto-scaffolding script:

```bash
# Generate story for a UI component
npm run generate:story Button

# Generate story for a dashboard widget
npm run generate:story dashboard/TeamAvailabilityWidget
```

Then update the generated story file with realistic props and variants.

### Component Coverage Status

#### Shell / Navigation
| Component | Story | Status |
|-----------|-------|--------|
| Layout variants (A/B/C/D/E) | ✅ `Layout.stories.tsx` | Complete |
| NavDropdown | ✅ `NavDropdown.stories.tsx` | Complete |

#### UI Components (Phase 1 — #467)
| Component | Story | Status |
|-----------|-------|--------|
| Button | ✅ `ui/Button.stories.tsx` | Complete |
| Input | ✅ `ui/Input.stories.tsx` | Complete |
| Select | ✅ `ui/Select.stories.tsx` | Complete |
| Checkbox | ✅ `ui/Checkbox.stories.tsx` | Complete |
| Radio | ✅ `ui/Radio.stories.tsx` | Complete |
| Toggle | ✅ `ui/Toggle.stories.tsx` | Complete |
| Textarea | ✅ `ui/Textarea.stories.tsx` | Complete |
| Card | ✅ `ui/Card.stories.tsx` | Complete |
| Modal | ✅ `ui/Modal.stories.tsx` | Complete |
| Tabs | ✅ `ui/Tabs.stories.tsx` | Complete |
| Table | ✅ `ui/Table.stories.tsx` | Complete |
| Breadcrumbs | ✅ `ui/Breadcrumbs.stories.tsx` | Complete |
| Toast | ✅ `ui/Toast.stories.tsx` | Complete |
| StatusBadge | ✅ `ui/StatusBadge.stories.tsx` | Complete |
| EmptyState | ✅ `ui/EmptyState.stories.tsx` | Complete |
| ConnectionStatus | ✅ `ui/ConnectionStatus.stories.tsx` | Complete |
| InfoTooltip | ✅ `ui/InfoTooltip.stories.tsx` | Complete |
| DropdownMenu | ✅ `ui/DropdownMenu.stories.tsx` | Complete |
| ConfirmPopover | ✅ `ui/ConfirmPopover.stories.tsx` | Complete |
| TableViewSelector | ✅ `ui/TableViewSelector.stories.tsx` | Complete |

#### Dashboard Widgets (Phase 2 — #468)
| Component | Story | Status |
|-----------|-------|--------|
| MetricCardGrid | ✅ `MetricCardGrid.stories.tsx` | Complete |
| RecentAlertsList | ✅ `dashboard/RecentAlertsList.stories.tsx` | Complete |
| DataQualitySummaryCard | ✅ `dashboard/DataQualitySummaryCard.stories.tsx` | Complete |
| OverdueItemsCard | ✅ `dashboard/OverdueItemsCard.stories.tsx` | Complete |
| PipelineSummaryChart | ✅ `dashboard/PipelineSummaryChart.stories.tsx` | Complete |
| CapacityGauge | ✅ `dashboard/CapacityGauge.stories.tsx` | Complete |
| FirmwareAlertsWidget | ✅ `dashboard/FirmwareAlertsWidget.stories.tsx` | Complete |
| TestExecutionCard | ✅ `dashboard/TestExecutionCard.stories.tsx` | Complete |
| TeamCapacityCard | ✅ `dashboard/TeamCapacityCard.stories.tsx` | Complete |
| TeamAvailabilityWidget | ✅ `dashboard/TeamAvailabilityWidget.stories.tsx` | Complete |

## Quick Links

### Foundations
- [Colors](./01-foundations/colors.md) - Color tokens, semantic system, dark mode
- [Typography](./01-foundations/typography.md) - Type scale, hierarchy, line height
- [Spacing](./01-foundations/spacing.md) - 4px grid system, component padding
- [Shadows](./01-foundations/shadows.md) - Elevation system for depth

### Components
- [Buttons](./02-components/buttons.md) - Variants, sizes, states, usage guidelines → [View in Storybook](http://localhost:6006/?path=/story/ui-button)
- [Navigation](./02-components/navigation.md) - NavDropdown, breadcrumbs, active states → [View in Storybook](http://localhost:6006/?path=/story/navdropdown)
- [Cards](./02-components/cards.md) - Card types, composition patterns, when to use each
- [Forms](./02-components/forms.md) - Input patterns, validation, error handling
- [Tables](./02-components/tables.md) - Data table patterns, density, sorting

💡 **Interactive examples**: Run `npm run storybook` to explore all stories with live controls and dark mode preview. All core UI components (20 stories) and dashboard widgets (10 stories) are covered. Use `npm run generate:story <component>` to scaffold stories for new components.

### Patterns
- [Page Shells](./03-patterns/page-shells.md) - Standard, wide, and full layout modes
- [Modal Flows](./03-patterns/modal-flows.md) - Dialog patterns, confirmation flows
- [Empty States](./03-patterns/empty-states.md) - Error, loading, no-data states
- [Support Actions](./03-patterns/support-actions.md) - Bug reporting, escalation, help

### Accessibility
- [WCAG Checklist](./04-accessibility/wcag-checklist.md) - WCAG 2.1 AA compliance
- [Keyboard Navigation](./04-accessibility/keyboard-nav.md) - Shortcuts, focus management
- [Screen Readers](./04-accessibility/screen-readers.md) - ARIA patterns, announcements

## Design Principles

### 1. Consistency Over Novelty
Use established patterns from the component library. Only create new components when existing ones don't meet the need.

### 2. Accessibility First
All components must meet WCAG 2.1 AA standards. Test with keyboard navigation and screen readers.

### 3. Progressive Enhancement
Design for mobile first, enhance for larger screens. Ensure core functionality works without JavaScript.

### 4. Performance Matters
Optimize for fast initial load. Lazy load heavy components. Use semantic HTML for better performance.

### 5. Content-Driven Design
Let content dictate layout needs. Use standard layout for forms, wide for tables, full for visualizations.

## Component Hierarchy

### Atomic Design Structure

**Atomic (Base Primitives)**
- Button, Input, Badge, Icon, StatusBadge
- Reusable across all contexts
- Minimal business logic

**Molecular (Composed Primitives)**
- Card, Modal, DropdownMenu, Select, DatePicker
- Combine atomic components
- Encapsulate common patterns

**Organisms (Feature Components)**
- MetricCardGrid, SummaryCards, DataTable, NavDropdown
- Business-specific composition
- May have internal state

**Templates (Page Shells)**
- Page layouts (standard, wide, full width)
- Navigation structure
- Footer placement

## Usage Guidelines

### Before Creating a New Component

1. **Check existing components**: Search `frontend/src/components/ui/` for similar functionality
2. **Review component docs**: Read the relevant component guide in `02-components/`
3. **Consider composition**: Can you achieve the need by composing existing components?
4. **Document the decision**: If creating a new component, document why in the component file

### When to Use Each Card Type

- **Metric Cards** (`MetricCardGrid`): Dashboard gauges with gradient backgrounds, icons, and trend indicators
- **Summary Cards** (`SummaryCards`): Static statistics with icon badges (Completed Tests page)
- **Content Cards** (`Card`): Generic content grouping with consistent padding and shadow

### Layout Mode Selection

- **Standard** (`max-w-7xl`): Forms, dashboards, visual-heavy pages - benefits from constrained line length
- **Wide** (`max-w-[96rem]`): Data tables with 5+ columns, drag-drop interfaces requiring spatial context
- **Full** (`max-w-full`): Timeline visualizations, Gantt charts, reports requiring maximum horizontal space

## Governance

### Component Review Process

1. **Propose**: Create an ADR (Architecture Decision Record) in `docs/design-system/adr/`
2. **Review**: Get sign-off from Critic agent (or QA lead)
3. **Document**: Update component guide in `02-components/`
4. **Implement**: Follow documented patterns
5. **Test**: Verify accessibility with keyboard + screen reader

### Preventing Component Proliferation

- Limit to one component per UI pattern
- Consolidate duplicates during regular audits
- Require justification for new components
- Prefer composition over creation

## Tech Stack

- **Framework**: React 18.3 with TypeScript 5.5
- **Styling**: Tailwind CSS 3.4 with custom primary color palette
- **Icons**: Heroicons 2.0 (24x24 outline)
- **Components**: shadcn/ui patterns with custom implementations
- **State**: Zustand (client), React Query (server)
- **Animation**: Tailwind transitions (hover, focus, transform)

## Contributing

See the upstream FW Testing Platform documentation for development workflow and code standards. (no CONTRIBUTING.md in this repo — these are reference snapshots only)

## Changelog

- **2026-02-23**: Initial design system documentation (Phase P4)
- **2026-02-23**: Layout width optimization system (Phase P3)
- **2026-02-23**: Global support footer and bug reporting (Phase P1-P2)
