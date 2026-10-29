from datetime import datetime


def wrap(content: str, title: str) -> str:
    """Page HTML des courriels de rapport : en-tête au titre du courriel, contenu, pied InvestAI."""
    return f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #1a1a2e;
            background-color: #f5f5f5;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 24px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 24px;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 16px 24px;
            text-align: center;
            font-size: 12px;
            color: #6c757d;
        }}
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            margin: 16px 0;
        }}
        .alert-box {{
            padding: 16px;
            border-radius: 6px;
            margin: 16px 0;
        }}
        .alert-success {{ background-color: #d4edda; color: #155724; }}
        .alert-warning {{ background-color: #fff3cd; color: #856404; }}
        .alert-danger {{ background-color: #f8d7da; color: #721c24; }}
        .alert-info {{ background-color: #d1ecf1; color: #0c5460; }}
        .metric {{
            display: inline-block;
            padding: 8px 16px;
            background-color: #f8f9fa;
            border-radius: 4px;
            margin: 4px;
        }}
        .metric-value {{
            font-size: 20px;
            font-weight: 600;
            color: #667eea;
        }}
        .metric-label {{
            font-size: 12px;
            color: #6c757d;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 16px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e9ecef;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
        }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
        </div>
        <div class="content">
            {content}
        </div>
        <div class="footer">
            <p>Cet email a ete envoye automatiquement par InvestAI.</p>
            <p>&copy; {datetime.now().year} InvestAI - Votre assistant d'investissement</p>
        </div>
    </div>
</body>
</html>
"""
