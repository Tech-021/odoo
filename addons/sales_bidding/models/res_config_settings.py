from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    daily_bid_target = fields.Integer(
        string="Daily Bid Target",
        default=40,
        config_parameter="sales_bidding.daily_bid_target",
        help="Default number of bids a salesperson should submit per day.",
    )

    freelancer_enabled = fields.Boolean(
        string="Enabled",
        config_parameter="sales_bidding.freelancer_enabled",
    )
    freelancer_client_id = fields.Char(
        string="Client ID", config_parameter="sales_bidding.freelancer_client_id"
    )
    freelancer_client_secret = fields.Char(
        string="Client Secret", config_parameter="sales_bidding.freelancer_client_secret"
    )
    freelancer_access_token = fields.Char(
        string="Access Token", config_parameter="sales_bidding.freelancer_access_token"
    )
    freelancer_refresh_token = fields.Char(
        string="Refresh Token", config_parameter="sales_bidding.freelancer_refresh_token"
    )
    freelancer_user_id = fields.Char(
        string="Freelancer User ID", config_parameter="sales_bidding.freelancer_user_id"
    )
    freelancer_odoo_user_id = fields.Many2one(
        "res.users",
        string="Odoo User (Reference)",
        config_parameter="sales_bidding.freelancer_odoo_user_id",
        help="Reference only. The shared Freelancer account is not mapped automatically; bidders claim imports themselves.",
    )
    freelancer_initial_sync_days = fields.Integer(
        string="Initial Sync Days",
        default=30,
        config_parameter="sales_bidding.freelancer_initial_sync_days",
        help="On the first sync, only import bids submitted within this many days.",
    )

    def action_sync_freelancer_bids(self):
        self.ensure_one()
        # Do not perform external HTTP requests inside the browser request.
        # Freelancer can be slow/unreachable, which would make the Odoo UI
        # appear disconnected while the request exceeds Odoo's time limit.
        cron = self.env.ref(
            "sales_bidding.ir_cron_sync_freelancer_bids"
        ).sudo()
        cron.write({"nextcall": fields.Datetime.now()})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Freelancer Sync Queued"),
                "message": _(
                    "The sync will run in the background. Check the Odoo log "
                    "for the completed import totals."
                ),
                "type": "success",
                "sticky": False,
            },
        }
