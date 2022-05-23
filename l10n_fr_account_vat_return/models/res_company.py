# Copyright 2021 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fr_vat_periodicity = fields.Selection(
        [
            ("1", "Monthly"),
            ("3", "Quarterly"),
            ("12", "Yearly"),
        ],
        default="1",
        string="VAT Periodicity",
    )
    fr_vat_exigibility = fields.Selection(
        [
            ("on_invoice", "Based on invoice"),
            ("on_payment", "Based on payment"),
            ("auto", "Both (automatic)"),
        ],
        default="on_invoice",
        string="VAT Exigibility",
    )
    fr_vat_update_lock_dates = fields.Boolean(
        string="Update Lock Date upon VAT Return Validation"
    )
    fr_vat_journal_id = fields.Many2one(
        "account.journal",
        string="Journal for VAT Journal Entry",
        ondelete="restrict",
        check_company=True,
    )
    fr_vat_expense_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account for Expense Adjustment",
        ondelete="restrict",
        check_company=True,
    )
    fr_vat_income_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Account for Income Adjustment",
        ondelete="restrict",
        check_company=True,
    )
    fr_vat_bank_account_id = fields.Many2one(
        "res.partner.bank",
        string="Company Bank Account",
        check_company=True,
        ondelete="restrict",
        help="Company bank account used to pay VAT or receive credit VAT reimbursements.",
    )

    @api.model
    def _test_fr_vat_create_company(self, company_name=None):  # noqa: C901
        # I write this method here and not in the test,
        # because it can be very useful for demos too
        self = self.sudo()
        afpo = self.env["account.fiscal.position"]
        afpao = self.env["account.fiscal.position.account"]
        afpto = self.env["account.fiscal.position.tax"]
        aao = self.env["account.account"]
        ato = self.env["account.tax"]
        atrlo = self.env["account.tax.repartition.line"]
        company = self.create(
            {
                "name": company_name or "FR Company VAT",
                "fr_vat_exigibility": "on_payment",
                "street": "42 rue du logiciel libre",
                "zip": "69009",
                "city": "Lyon",
                "country_id": self.env.ref("base.fr").id,
                "siret": "77788899100018",
                "vat": "FR51777888991",
            }
        )
        self.env.user.write({"company_ids": [(4, company.id)]})
        fr_chart_template = self.env.ref("l10n_fr.l10n_fr_pcg_chart_template")
        fr_chart_template._load(20.0, 20.0, company)
        od_journal = self.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "general")], limit=1
        )
        company.write({"fr_vat_journal_id": od_journal.id})
        # Update PCG
        # delete some accounts
        accounts_to_del = aao.search(
            [
                ("company_id", "=", company.id),
                ("code", "in", ("701200", "707200", "445710")),
            ]
        )
        accounts_to_del.unlink()

        # create accounts
        revenue_accounts = [
            ("701200", "Vt produits finis UE B2B"),
            ("701300", "Vt produits finis UE B2C"),
            ("701400", "Vt produits finis reste du monde"),
            ("701500", "Vt produits finis France exonéré"),
            ("706200", "Prestation de service UE B2B"),
            ("706300", "Prestation de service UE B2C"),
            ("706400", "Prestation de service reste du monde"),
            ("706500", "Prestation de service France exonéré"),
            ("707200", "Vt marchandises UE B2B"),
            ("707300", "Vt marchandises UE B2C"),
            ("707400", "Vt marchandises reste du monde"),
            ("707500", "Vt marchandises France exonéré"),
            ("708520", "Frais de port UE B2B"),
            ("708530", "Frais de port UE B2C"),
            ("708540", "Frais de port reste du monde"),
            ("708550", "Frais de port France exonéré"),
        ]
        revenue_type_id = self.env.ref("account.data_account_type_revenue").id
        for acc_code, acc_name in revenue_accounts:
            aao.create(
                {
                    "company_id": company.id,
                    "code": acc_code,
                    "name": acc_name,
                    "user_type_id": revenue_type_id,
                    "reconcile": False,
                }
            )
        fr_account_codes = ["701100", "706000", "707100", "708500"]
        for fr_account_code in fr_account_codes:
            account = aao.search(
                [("company_id", "=", company.id), ("code", "=", fr_account_code)]
            )
            new_name = "%s France" % account.name
            account.write({"name": new_name})

        # update fiscal positions
        fp2type = {
            "fiscal_position_template_intraeub2b": "intracom_b2b",
            "fiscal_position_template_domestic": "france",
            "fiscal_position_template_import_export": "extracom",
            "fiscal_position_template_intraeub2c": "intracom_b2c",
        }
        type2map = {
            "intracom_b2b": [
                ("701100", "701200"),
                ("706000", "706200"),
                ("707100", "707200"),
                ("708500", "708520"),
            ],
            "intracom_b2c": [
                ("701100", "701300"),
                ("706000", "706300"),
                ("707100", "707300"),
                ("708500", "708530"),
            ],
            "extracom": [
                ("701100", "701400"),
                ("706000", "706400"),
                ("707100", "707400"),
                ("708500", "708540"),
            ],
            "france_exo": [
                ("701100", "701500"),
                ("706000", "706500"),
                ("707100", "707500"),
                ("708500", "708550"),
            ],
        }
        fptype2fp = {}
        for fp_xmlid_suffix, fp_type in fp2type.items():
            xmlid = "l10n_fr.%d_%s" % (company.id, fp_xmlid_suffix)
            fp = self.env.ref(xmlid)
            fp.write(
                {
                    "fr_vat_type": fp_type,
                    "auto_apply": False,
                }
            )
            fptype2fp[fp_type] = fp
            if type2map.get(fp_type):
                for (src_acc_code, dest_acc_code) in type2map[fp_type]:
                    afpao.create(
                        {
                            "position_id": fp.id,
                            "account_src_id": aao.search(
                                [
                                    ("company_id", "=", company.id),
                                    ("code", "=", src_acc_code),
                                ]
                            ).id,
                            "account_dest_id": aao.search(
                                [
                                    ("company_id", "=", company.id),
                                    ("code", "=", dest_acc_code),
                                ]
                            ).id,
                        }
                    )
        # delete on_payment taxes
        taxes_to_del = ato.search(
            [("company_id", "=", company.id), ("tax_exigibility", "=", "on_payment")]
        )
        tax_map_to_del = afpto.search(
            [("company_id", "=", company.id), ("tax_src_id", "in", taxes_to_del.ids)]
        )
        tax_map_to_del.unlink()
        taxes_to_del.unlink()
        # Create France exo FP
        france_exo_fp = afpo.create(
            {
                "name": "France exonéré",
                "fr_vat_type": "france_exo",
                "auto_apply": False,
                "company_id": company.id,
            }
        )
        fptype2fp["france_exo"] = france_exo_fp
        for (src_acc_code, dest_acc_code) in type2map["france_exo"]:
            afpao.create(
                {
                    "position_id": france_exo_fp.id,
                    "account_src_id": aao.search(
                        [
                            ("company_id", "=", company.id),
                            ("code", "=", src_acc_code),
                        ]
                    ).id,
                    "account_dest_id": aao.search(
                        [
                            ("company_id", "=", company.id),
                            ("code", "=", dest_acc_code),
                        ]
                    ).id,
                }
            )
        # I use extracom FP to get the list of source taxes
        extracom_fp = fptype2fp["extracom"]
        sale_tax_dest_xmlid = "l10n_fr.%d_tva_0" % company.id
        sale_tax_dest_id = self.env.ref(sale_tax_dest_xmlid).id
        # There is no puchase 0% tax provided in l10n_fr
        purchase_tax_dest_id = ato.create(
            {
                "company_id": company.id,
                "name": "TVA 0% (achat)",
                "description": "TVA 0%",
                "amount": 0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "tax_group_id": self.env.ref("l10n_fr.tax_group_tva_0").id,
                "invoice_repartition_line_ids": [
                    (
                        0,
                        0,
                        {
                            "factor_percent": 100,
                            "repartition_type": "base",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "factor_percent": 100,
                            "repartition_type": "tax",
                        },
                    ),
                ],
                "refund_repartition_line_ids": [
                    (
                        0,
                        0,
                        {
                            "factor_percent": 100,
                            "repartition_type": "base",
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "factor_percent": 100,
                            "repartition_type": "tax",
                        },
                    ),
                ],
            }
        ).id

        for extracom_tax_line in extracom_fp.tax_ids:
            if extracom_tax_line.tax_src_id.type_tax_use == "sale":
                tax_dest_id = sale_tax_dest_id
            else:
                tax_dest_id = purchase_tax_dest_id
            afpto.create(
                {
                    "position_id": france_exo_fp.id,
                    "tax_src_id": extracom_tax_line.tax_src_id.id,
                    "tax_dest_id": tax_dest_id,
                }
            )

        # Update regular FR VAT taxes
        tax_type_id = self.env.ref("account.data_account_type_current_liabilities").id
        rate2account = {
            2000: "445711",
            1000: "445712",
            850: "445713",
            550: "445714",
            210: "445715",
        }
        for rate, acc_code in rate2account.items():
            rate_label = "%s %% " % str(rate / 100).replace(".", ",")
            tax_account_id = aao.create(
                {
                    "code": acc_code,
                    "name": "TVA collectée %s" % rate_label,
                    "company_id": company.id,
                    "reconcile": True,
                    "user_type_id": tax_type_id,
                }
            ).id
            rate2account[rate] = tax_account_id

        intracom_fp = fptype2fp["intracom_b2b"]
        for tline in intracom_fp.tax_ids:
            if tline.tax_src_id.type_tax_use == "sale":
                tax = tline.tax_src_id
                rate = int(round(tax.amount * 100))
                if rate in rate2account:
                    lines = atrlo.search(
                        [
                            "|",
                            ("invoice_tax_id", "=", tax.id),
                            ("refund_tax_id", "=", tax.id),
                            ("repartition_type", "=", "tax"),
                        ]
                    )
                    lines.write({"account_id": rate2account[rate]})
        # Update intracom and extracom autoliq taxes
        tracom_dict = {
            "intracom_b2b": {
                2000: "445201",
                1000: "445202",
                850: "445203",
                550: "445204",
                210: "445205",
                "deduc": "445662",
                "label": "acquisitions intracommunautaire",
            },
            "extracom": {
                2000: "445301",
                1000: "445302",
                850: "445303",
                550: "445304",
                210: "445305",
                "deduc": "445663",
                "label": "acquisitions extracommunautaire",
            },
        }
        for fp_type, wdict in tracom_dict.items():
            fp = fptype2fp[fp_type]
            deduc_tax_account_id = aao.create(
                {
                    "code": wdict["deduc"],
                    "name": "TVA déductible %s" % wdict["label"],
                    "company_id": company.id,
                    "reconcile": True,
                    "user_type_id": tax_type_id,
                }
            ).id
            for tax_line in fp.tax_ids:
                if tax_line.tax_dest_id.type_tax_use == "purchase":
                    tax = tax_line.tax_dest_id
                    tax_rate = int(round(tax.amount * 100))
                    rate_label = "%s %% " % str(tax_rate / 100).replace(".", ",")
                    if tax_rate in wdict:
                        acc_code = wdict[tax_rate]
                        due_tax_account_id = aao.create(
                            {
                                "code": acc_code,
                                "name": "TVA due %s %s" % (wdict["label"], rate_label),
                                "company_id": company.id,
                                "reconcile": True,
                                "user_type_id": tax_type_id,
                            }
                        ).id
                        deduc_lines = atrlo.search(
                            [
                                "|",
                                ("invoice_tax_id", "=", tax.id),
                                ("refund_tax_id", "=", tax.id),
                                ("repartition_type", "=", "tax"),
                                ("factor_percent", ">", 99),  # = 100
                            ]
                        )
                        deduc_lines.write({"account_id": deduc_tax_account_id})
                        due_lines = atrlo.search(
                            [
                                "|",
                                ("invoice_tax_id", "=", tax.id),
                                ("refund_tax_id", "=", tax.id),
                                ("repartition_type", "=", "tax"),
                                ("factor_percent", "<", -99),  # = -100
                            ]
                        )
                        due_lines.write({"account_id": due_tax_account_id})
        return company
