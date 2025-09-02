from frappe import _

def get_data():
    return {
        'fieldname': 'project',
        'transactions': [
            {
                'label': _('Sales'),
                'items': ['Sales Order Item']
            }
        ]
    }
