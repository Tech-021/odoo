{
    "name": "Sales Bidding",
    "version": "1.0.0",
    "category": "Sales",
    "summary": "Track Upwork and Freelancer bidding activity",
    "author": "Tech-021",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/sales_bidding_security.xml",
        "security/ir.model.access.csv",
        "data/freelancer_cron.xml",
        "views/sales_bid_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/sales_bid_import_wizard_views.xml",
    ],
    "assets": {
    "web.assets_backend": [
            "sales_bidding/static/src/sales_bid_my_list/sales_bid_my_list.xml",
            "sales_bidding/static/src/sales_bid_my_list/sales_bid_my_list.js",
            "sales_bidding/static/src/sales_bid_my_list/sales_bid_my_list.scss",
        ],
    },
    "installable": True,
    "application": True,
}
