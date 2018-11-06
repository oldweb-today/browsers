FROM python:3.5.3

WORKDIR /app

ADD requirements.txt /app

RUN pip install -r requirements.txt

ADD . /app

RUN wget -P ./app/static/ https://raw.githubusercontent.com/oldweb-today/shepherd-client/master/dist/shepherd-client.bundle.js

CMD python -u app.py


