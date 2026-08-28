# AssetTrack 360 Search Indexing Setup REV03

## Public URLs
- https://assettrack360.wykiesautomation.co.za/
- https://assettrack360.wykiesautomation.co.za/register
- https://assettrack360.wykiesautomation.co.za/login
- https://assettrack360.wykiesautomation.co.za/plans

## Search discovery URLs
- https://assettrack360.wykiesautomation.co.za/robots.txt
- https://assettrack360.wykiesautomation.co.za/sitemap.xml
- https://assettrack360.wykiesautomation.co.za/site.webmanifest

## Private paths
Dashboard, assets, devices, billing, integrations, API and onboarding routes receive an `X-Robots-Tag: noindex` response header and are excluded from the sitemap.

## Render environment variables
Keep `PUBLIC_BASE_URL=https://assettrack360.wykiesautomation.co.za`.
Optional verification variables:
- `BING_SITE_VERIFICATION`
- `GOOGLE_SITE_VERIFICATION`

## Bing Webmaster Tools
1. Add `https://assettrack360.wykiesautomation.co.za`.
2. Verify ownership using the Bing verification token stored in Render as `BING_SITE_VERIFICATION`.
3. Submit `https://assettrack360.wykiesautomation.co.za/sitemap.xml`.
4. Use URL Inspection / Submit URL for the public home page.

## Validation after deploy
Open `/robots.txt`, `/sitemap.xml` and `/site.webmanifest` directly. The public home source should contain canonical, description, Open Graph and JSON-LD metadata. Logged-in/private pages should include `X-Robots-Tag: noindex` in response headers.
