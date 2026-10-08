import reflex as rx

config = rx.Config(
    app_name="projetoImpacta",
    env_file=".env",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="dark", accent_color="teal", has_background=False),
        ),
    ]
)