from datetime import datetime, time, timedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo import _, api, fields, models

class SalesBid(models.Model):
    _name = "sales.bid"
    _description = "Sales Bid"
    _order = "bid_date desc"

    name = fields.Char(
        string="Project / Client",
        required=True,
    )

    salesperson_id = fields.Many2one(
        comodel_name="res.users",
        string="Salesperson",
        # Manual and CSV bids still default to the current user.  Imported
        # Freelancer bids are initially unassigned and are claimed later.
        required=False,
        default=lambda self: self.env.user,
        domain=lambda self: self._salesperson_domain(),
    )

    freelancer_bid_id = fields.Char(
        string="Freelancer Bid ID",
        copy=False,
        index=True,
        readonly=True,
    )

    freelancer_project_id = fields.Char(
        string="Freelancer Project ID",
        copy=False,
        readonly=True,
    )

    platform = fields.Selection(
        selection=[
            ("upwork", "Upwork"),
            ("freelancer", "Freelancer"),
        ],
        string="Platform",
        required=True,
        default="upwork",
    )

    job_url = fields.Char(
        string="Job URL",
        required=True,
    )

    bid_amount = fields.Float(
        string="Bid Amount",
        default=0.0,
    )

    bid_type = fields.Selection(
        selection=[
            ("fixed", "Fixed Price"),
            ("hourly", "Hourly"),
        ],
        string="Bid Type",
        required=True,
        default="fixed",
    )

    status = fields.Selection(
        selection=[
            ("submitted", "Submitted"),
            ("responded", "Responded"),
            ("interview", "Interview"),
            ("won", "Won"),
            ("lost", "Lost"),
        ],
        string="Status",
        required=True,
        default="submitted",
    )

    bid_date = fields.Datetime(
        string="Bid Date",
        required=True,
        default=fields.Datetime.now,
    )

    notes = fields.Text(
        string="Notes",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    _freelancer_bid_id_unique = models.Constraint(
        "unique(platform, freelancer_bid_id)",
        "A Freelancer bid can only be imported once.",
    )

    @api.model
    def _salesperson_domain(self):
        if self.env.user.has_group("sales_bidding.group_sales_bidding_manager"):
            user_group = self.env.ref("sales_bidding.group_sales_bidding_user")
            manager_group = self.env.ref("sales_bidding.group_sales_bidding_manager")
            return [("all_group_ids", "in", [user_group.id, manager_group.id])]
        return [("id", "=", self.env.user.id)]

    def action_claim_freelancer_bid(self):
        self.ensure_one()
        if self.platform != "freelancer" or not self.freelancer_bid_id:
            raise UserError(_("Only imported Freelancer bids can be claimed."))
        if self.salesperson_id:
            raise UserError(_("This bid has already been assigned to another bidder."))

        # Atomic update protects two bidders claiming the same row at once.
        self.env.cr.execute(
            """UPDATE sales_bid
               SET salesperson_id = %s, write_date = NOW()
             WHERE id = %s AND salesperson_id IS NULL""",
            (self.env.user.id, self.id),
        )
        if self.env.cr.rowcount != 1:
            self.invalidate_recordset(["salesperson_id"])
            raise UserError(_("This bid has already been assigned to another bidder."))
        self.invalidate_recordset(["salesperson_id"])
        return True

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group(
            "sales_bidding.group_sales_bidding_manager"
        ):
            vals_list = [dict(vals, salesperson_id=self.env.user.id) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if (
            "salesperson_id" in vals
            and not self.env.su
            and not self.env.user.has_group("sales_bidding.group_sales_bidding_manager")
            and vals["salesperson_id"] != self.env.user.id
        ):
            raise AccessError(_("You can only assign a bid to yourself."))
        return super().write(vals)

    daily_bid_target = fields.Integer(
        string="Daily Bid Target",
        compute="_compute_daily_bid_achievement",
    )

    daily_bid_count = fields.Integer(
        string="Today's Bids",
        compute="_compute_daily_bid_achievement",
    )

    daily_achievement = fields.Float(
        string="Daily Achievement %",
        compute="_compute_daily_bid_achievement",
    )

    @api.model
    def get_my_today_stats(self):
        today = fields.Date.context_today(self)
        start = datetime.combine(today, time.min)
        end = start + timedelta(days=1)

        target = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "sales_bidding.daily_bid_target", default=40
            )
        )

        count = self.search_count([
            ("salesperson_id", "=", self.env.user.id),
            ("bid_date", ">=", start),
            ("bid_date", "<", end),
        ])

        return {
            "target": target,
            "count": count,
            "achievement": (count / target) * 100 if target > 0 else 0.0,
        }

    @api.constrains("bid_date")
    def _check_bid_date_not_future(self):
        today = fields.Date.context_today(self)
        for record in self:
            if record.bid_date and fields.Date.to_date(record.bid_date) > today:
                raise ValidationError(_("Bid date cannot be in the future."))

    @api.depends("salesperson_id", "bid_date")
    def _compute_daily_bid_achievement(self):
        target = int(
            self.env["ir.config_parameter"].sudo().get_param(
                "sales_bidding.daily_bid_target",
                default=40,
            )
        )

        for record in self:
            record.daily_bid_target = target

            if not record.salesperson_id:
                record.daily_bid_count = 0
                record.daily_achievement = 0.0
                continue

            today = fields.Date.context_today(record)

            start_datetime = datetime.combine(
                today,
                time.min,
            )

            end_datetime = start_datetime + timedelta(days=1)

            daily_count = self.search_count([
                ("salesperson_id", "=", record.salesperson_id.id),
                ("bid_date", ">=", start_datetime),
                ("bid_date", "<", end_datetime),
            ])

            record.daily_bid_count = daily_count

            if target > 0:
                record.daily_achievement = (
                    daily_count / target
                ) * 100
            else:
                record.daily_achievement = 0.0
