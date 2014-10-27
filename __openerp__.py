{
    'name': "Tempo HR",
    'author': 'Stéphane Codazzi @ TeMPO-Consulting',
    'category': 'Project',
    'description': """
Tempo HR
=========================
    """,
    'version': '0.1',
    'depends': ['public_holidays', 'hr_contract', 'hr_attendance', 'hr', 'calendar', 'resource', 'hr_holidays'],
    'data': [
        'static/src/xml/view.xml',
        'static/src/xml/edit.xml',
    ],
}
