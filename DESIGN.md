# Design System Specification: The Architectural Insight

## 1. Overview & Creative North Star
**Creative North Star: "The Precision Curator"**

This design system is engineered to transform dense inventory logistics and performance metrics into a high-end editorial experience. We are moving away from the "cluttered dashboard" trope and toward a "Digital Gallery" aesthetic. By leveraging **intentional asymmetry**, **extreme white space**, and **tonal layering**, we create a sense of calm authority. 

The system breaks the "bootstrap template" look by treating data as art. We use a high-contrast typography scale to create an immediate information hierarchy, ensuring that even in a data-heavy environment, the user’s eye is led purposefully through the interface rather than being overwhelmed by a sea of uniform boxes.

---

## 2. Colors & Surface Philosophy
The palette is rooted in a deep, intellectual indigo and supported by a sophisticated range of slates.

### The "No-Line" Rule
**Prohibit 1px solid borders for sectioning.** Traditional borders create visual noise that traps data. Instead, define boundaries through:
*   **Background Shifts:** Place a `surface_container_lowest` card atop a `surface_container_low` background.
*   **Tonal Transitions:** Use the `surface` scale to create distinct zones of activity.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers. We use a "Nested Depth" approach:
1.  **Base Layer:** `surface` (#f7f9fb) – The canvas.
2.  **Sectional Layer:** `surface_container_low` (#f2f4f6) – For large grouping areas like the sidebar or secondary content zones.
3.  **Action Layer:** `surface_container_lowest` (#ffffff) – For primary data cards and interactive elements. This creates a "lifted" effect without heavy shadows.

### The "Glass & Gradient" Rule
To inject "soul" into the portal, main CTAs and hero performance metrics should utilize a subtle linear gradient: `primary` (#3525cd) to `primary_container` (#4f46e5). For floating elements like tooltips or dropdowns, apply **Glassmorphism**: use `surface_container_lowest` at 80% opacity with a `backdrop-blur` of 12px.

---

## 3. Typography: Editorial Authority
We utilize a pairing of **Manrope** for high-impact displays and **Inter** for functional data clarity.

*   **Display & Headlines (Manrope):** Used for "Big Numbers" and section headers. The wider aperture of Manrope conveys modernism and confidence.
    *   *Display-LG:* `3.5rem` / Tight tracking (-0.02em). Use for hero performance percentages.
*   **Titles & Body (Inter):** Used for labels, table data, and descriptions. Inter is chosen for its exceptional legibility at small sizes.
    *   *Title-MD:* `1.125rem` / Medium weight. For card headings.
    *   *Body-MD:* `0.875rem` / Regular weight. For standard data entry.

**Hierarchy Note:** Always maintain a 2:1 ratio between headline and body text size to ensure a signature "Editorial" look.

---

## 4. Elevation & Depth
In this system, depth is felt, not seen. We reject the "heavy drop shadow."

*   **The Layering Principle:** Stack `surface_container_highest` for utility bars (like table headers) and `surface_container_lowest` for the table rows themselves.
*   **Ambient Shadows:** For floating modals, use a custom shadow: `0px 20px 40px rgba(25, 28, 30, 0.06)`. The shadow color is derived from `on_surface` to keep it natural.
*   **The Ghost Border Fallback:** If a divider is mandatory for accessibility, use `outline_variant` (#c7c4d8) at **15% opacity**. It should be a whisper, not a statement.

---

## 5. Components

### High-Contrast Value Cards
*   **Structure:** No borders. Background: `surface_container_lowest`. 
*   **Styling:** Left-align the `label-md` (Metric Name) and use `display-md` for the value. 
*   **Signature Element:** A subtle 4px vertical accent bar on the left edge using the `primary` color to denote "Active" or "Selected" status.

### Searchable Data Tables
*   **Header:** Use `surface_container_high` with `label-sm` typography in all caps with 0.05em letter spacing.
*   **Rows:** Separated by `1.5` (0.5rem) of vertical whitespace rather than lines. 
*   **Interaction:** On hover, shift the row background to `primary_fixed` at 30% opacity.

### Persistent Sidebar
*   **Width:** `12` (4rem) collapsed / `16` (5.5rem) expanded.
*   **Background:** `surface_container_low`.
*   **Active State:** Avoid "glows." Use a `primary` color icon and a `primary_fixed` pill background with a `xl` (0.75rem) border radius.

### Modals & Data Entry
*   **Form Fields:** Use `surface_container_lowest`. Borders are replaced by a 2px bottom-stroke of `outline_variant` that transitions to `primary` on focus.
*   **Modals:** Use a `surface_blur` backdrop (Glassmorphism). The modal itself should have an `xl` corner radius and no visible close button—use a "Click Outside" or "Esc" pattern to keep the UI clean.

### Chart.js Visualizations
*   **Palette:** Use `primary`, `secondary`, and `tertiary` for data series. 
*   **Gridlines:** Set `display: false` for all X-axis gridlines. Y-axis lines should be `outline_variant` at 10% opacity.
*   **Point Style:** Use 'circle' with a `primary` stroke and `surface_container_lowest` fill.

---

## 6. Do’s and Don’ts

### Do
*   **Do** use the `20` (7rem) spacing token for top-level page margins to create a "Gallery" feel.
*   **Do** utilize `primary_container` for secondary buttons to maintain brand presence without competing with the Primary CTA.
*   **Do** use `surface_container_highest` for "Empty State" illustrations to keep them integrated into the background.

### Don't
*   **Don't** use 100% black (#000000) for text. Always use `on_surface` (#191c1e) to maintain a premium, ink-on-paper feel.
*   **Don't** use standard `lg` (0.5rem) rounding for everything. Use `full` for tags/chips and `xl` for large cards to create a sophisticated "Soft-Modern" contrast.
*   **Don't** ever use a solid 1px divider to separate table columns. Use the spacing scale to create clear gutters.