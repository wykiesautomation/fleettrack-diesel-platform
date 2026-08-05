import json
import os
from datetime import datetime, timezone
from flask import Blueprint, Response, current_app, request, url_for

seo_bp = Blueprint('seo', __name__)

PUBLIC_BASE_URL = os.getenv(
    'PUBLIC_BASE_URL',
    'https://fleettrack.wykiesautomation.co.za',
).rstrip('/')

PUBLIC_PATHS = (
    ('/', 'daily', '1.0'),
    ('/register', 'weekly', '0.9'),
    ('/login', 'monthly', '0.5'),
    ('/plans', 'weekly', '0.8'),
)

PRIVATE_PREFIXES = (
    '/dashboard', '/asset/', '/devices', '/account', '/billing',
    '/integrations', '/edge-gateways', '/api/', '/onboarding',
    '/subscription-required',
)

@seo_bp.get('/robots.txt')
def robots_txt():
    body = f'''User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /asset/
Disallow: /devices
Disallow: /account
Disallow: /billing
Disallow: /integrations
Disallow: /edge-gateways
Disallow: /api/
Disallow: /onboarding

Sitemap: {PUBLIC_BASE_URL}/sitemap.xml
'''
    return Response(body, mimetype='text/plain')

@seo_bp.get('/sitemap.xml')
def sitemap_xml():
    today = datetime.now(timezone.utc).date().isoformat()
    rows = []
    for path, changefreq, priority in PUBLIC_PATHS:
        rows.append(
            f'''  <url>\n'''
            f'''    <loc>{PUBLIC_BASE_URL}{path}</loc>\n'''
            f'''    <lastmod>{today}</lastmod>\n'''
            f'''    <changefreq>{changefreq}</changefreq>\n'''
            f'''    <priority>{priority}</priority>\n'''
            f'''  </url>'''
        )
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(rows)
    xml += '\n</urlset>\n'
    return Response(xml, mimetype='application/xml')

@seo_bp.get('/site.webmanifest')
def webmanifest():
    body = {
        'name': 'AssetTrack 360',
        'short_name': 'AssetTrack 360',
        'description': 'Secure fleet, diesel, tank and connected-asset monitoring.',
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#061622',
        'theme_color': '#083344',
    }
    return Response(json.dumps(body), mimetype='application/manifest+json')

def _public_home_metadata():
    title = 'AssetTrack 360 | Fleet, Diesel and Asset Monitoring South Africa'
    description = (
        'Track vehicles, review location history, monitor diesel and tank levels, '
        'receive alarms and manage secure connected devices with AssetTrack 360.'
    )
    canonical = f'{PUBLIC_BASE_URL}/'
    structured = {
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        'name': 'AssetTrack 360',
        'applicationCategory': 'BusinessApplication',
        'operatingSystem': 'Web',
        'url': canonical,
        'description': description,
        'offers': {
            '@type': 'Offer',
            'priceCurrency': 'ZAR',
            'availability': 'https://schema.org/OnlineOnly',
        },
        'provider': {
            '@type': 'Organization',
            'name': 'Wykies Automation',
            'url': 'https://wykiesautomation.co.za',
        },
    }
    return title, description, canonical, structured

def register_seo_hooks(app):
    @app.after_request
    def apply_search_headers_and_metadata(response):
        path = request.path
        if path.startswith(PRIVATE_PREFIXES):
            response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        elif path in ('/', '/register', '/login', '/plans'):
            response.headers['X-Robots-Tag'] = 'index, follow, max-image-preview:large'

        if (
            path == '/'
            and response.status_code == 200
            and response.content_type.startswith('text/html')
        ):
            html = response.get_data(as_text=True)
            if '</head>' in html and 'data-assettrack-seo="1"' not in html:
                title, description, canonical, structured = _public_home_metadata()
                bing = os.getenv('BING_SITE_VERIFICATION', '').strip()
                google = os.getenv('GOOGLE_SITE_VERIFICATION', '').strip()
                verification = ''
                if bing:
                    verification += f'<meta name="msvalidate.01" content="{bing}">\n'
                if google:
                    verification += f'<meta name="google-site-verification" content="{google}">\n'
                tags = f'''\n<!-- AssetTrack 360 public search metadata -->
<meta data-assettrack-seo="1" name="description" content="{description}">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#083344">
<meta property="og:type" content="website">
<meta property="og:site_name" content="AssetTrack 360">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
{verification}<script type="application/ld+json">{json.dumps(structured)}</script>
'''
                html = html.replace('</head>', tags + '</head>', 1)
                if '<title>' in html and '</title>' in html:
                    start = html.index('<title>')
                    end = html.index('</title>', start) + len('</title>')
                    html = html[:start] + f'<title>{title}</title>' + html[end:]
                response.set_data(html)
                response.headers['Content-Length'] = str(len(response.get_data()))
        return response
