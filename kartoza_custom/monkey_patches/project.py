# my_app/overrides/project.py

from erpnext.projects.doctype.project.project import Project


class CustomProject(Project):

    def validate(self):
        # preserve user values
        user_percent = self.percent_complete
        user_sales = self.total_sales_amount

        super().validate()

        self.percent_complete = user_percent
        self.total_sales_amount = user_sales