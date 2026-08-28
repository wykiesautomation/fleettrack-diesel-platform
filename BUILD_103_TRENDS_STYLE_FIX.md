# Build 103 Trends Styling Fix

Root cause: page-specific stylesheets were loaded before `rev28_full.css`, allowing broad global rules to override the Trends layout. The base template now loads global REV28 CSS first and page-specific CSS afterward. Strong scoped Trends rules restore the selected-device grid, assigned-pin chips, four-column fields, tabs and save bar.
