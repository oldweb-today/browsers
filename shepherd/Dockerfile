FROM python:3.5.2
MAINTAINER Ilya Kreymer <ikreymer at gmail.com>

WORKDIR /app

ADD requirements.txt /app/

RUN pip install -r requirements.txt

ADD . /app/

CMD ["uwsgi", "uwsgi.ini"]


