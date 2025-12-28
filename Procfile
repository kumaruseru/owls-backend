web: python manage.py migrate && gunicorn backend.wsgi:application --worker-class gthread --threads 4 --bind 0.0.0.0:$PORT
