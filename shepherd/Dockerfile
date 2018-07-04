FROM python:3.5.2
MAINTAINER Ilya Kreymer <ikreymer at gmail.com>

WORKDIR /shepherd

ADD requirements.txt /shepherd/

RUN pip install -r requirements.txt

ADD . /shepherd/

RUN for file in "/shepherd/static/browser.js" \
                 "/shepherd/static/audio_opus.js" \
                  ; \
       do cat $file && echo "\n" ; done  \
       > /shepherd/static/browser_controller.js

VOLUME /shepherd/static/

RUN nose2 --with-coverage

CMD ["uwsgi", "uwsgi.ini"]


