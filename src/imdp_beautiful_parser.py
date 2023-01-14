import csv
import os
import sys
import time
import requests
from bs4 import BeautifulSoup
import re

base_url = 'https://www.imdb.com'
reviews_url = "https://www.imdb.com/title/{}/reviews"
reviews_dir = '../data/reviews_2/'
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}


def parse_top_1000():
    url = 'https://www.imdb.com/search/title/'
    params = {'groups': 'top_1000', 'sort': 'user_rating,desc', 'view': 'simple', 'count': 100}
    result = []
    for i in range(1, 1000, 100):
        params['start'] = i
        response = requests.get(url, headers=headers, params=params)
        time.sleep(1)
        soup = BeautifulSoup(response.content, "html.parser")
        print(i)
        parse_page(soup, result)
    with open('../data/top_1000_movies.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerows(result)


def parse_page(soup, result):
    movies = soup.find_all("div", class_="lister-col-wrapper")
    for movie in movies:
        title_column = movie.find("span", class_='lister-item-header').find('a')
        title = title_column.text
        match = re.search("tt\d+", title_column['href'])
        link = title_column['href'][match.start():match.end()]
        rating = movie.find("div", class_='col-imdb-rating').text.replace('\\n', '').strip()
        print(title, link, rating)
        result.append([title, link, rating])


def parse_top_1000_movies_reviews():
    parsed = {}
    with open('../data/parsed_movies_3.csv', 'r') as f_parsed:
        reader = csv.reader(f_parsed)
        for row in reader:
            parsed.update({row[1]: row})

    with open('../data/top_1000_movies.csv') as f:
        reader = csv.reader(f)
        # reader = [["test", 'tt0026778', 7.7]]
        for index, row in enumerate(reader, 1):
            if index < 1:
                continue
            title, title_num, score = row
            filename = f"{reviews_dir}{index}_{title_num}"

            url = reviews_url.format(title_num)
            print("____________________________________________________________")
            print(f'{time.strftime("%d %b %H:%M:%S", time.localtime())}')
            print(f'"{index} |{title}" filename: {filename} url: {url}')

            parsed_movie = parsed.get(title_num)
            if parsed_movie:
                print(f"Already got {parsed_movie[2]} reviews out of {parsed_movie[3]} "
                      f"for {parsed_movie[0]} Diff ={parsed_movie[4]}")

                answer_text = input("Do you want to parse this again?")
                if answer_text != 'y':
                    print('Skipped')
                    continue

            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.content, "html.parser")

            header = soup.find("div", class_="header")
            if header and header.find("div"):
                header_text = header.find("div").text
                reviews_count_total = int(re.sub('[^0-9]', '', header_text))
                print(f"Parsing {header_text} ({reviews_count_total})")

            reviews = parse_movie_review(url + '/_ajax', [])
            reviews_count_parsed = len(reviews)
            print(f"Final Reviews Count = {reviews_count_parsed} out of {reviews_count_total}")
            with open(filename, 'w') as f_reviews:
                for review in reviews:
                    f_reviews.write(f"{review}\n")
            checked = check_parsed_reviews(title_num, filename)
            print(f"checked = {checked}")
            if checked:
                with open('../data/parsed_movies_3.csv', 'a+') as f_parsed:
                    csv.writer(f_parsed).writerow([
                        index,
                        time.strftime("%d %b %H:%M:%S", time.localtime()),
                        title,
                        title_num,
                        reviews_count_parsed,
                        reviews_count_total,
                        reviews_count_total - reviews_count_parsed,
                        url
                    ])

            time.sleep(0.7)


def write_error_movie(text):
    with open('../data/error_movies.csv', 'a+') as f_error:
        f_error.write(text)
    print(f"error movie {text}")


def parse_movie_review(url, reviews, params=None):
    print(
        f'{time.strftime("%d %b %H:%M:%S", time.localtime())} Got \033[1m{len(reviews)}\033[0m reviews. Getting more...')
    if params is None:
        params = {}
    try:
        response = requests.get(url, headers=headers, params=params)
    except ConnectionError as e:
        write_error_movie(url)
        print(f"at {url} with {params} Error: {e}")
        return []
    else:
        soup = BeautifulSoup(response.content, "html.parser")
        new_reviews = [re.sub('\n', '', x.text) for x in soup.find_all("div", class_="text show-more__control")]
        reviews.extend(new_reviews)

        load_more = soup.find('div', class_='load-more-data')

        if load_more:
            pagination_key = load_more['data-key']
            params = {'paginationKey': pagination_key}
            time.sleep(0.2)
            parse_movie_review(url, reviews, params)

    return reviews


def read_all_reviews_files():
    for filename in os.listdir(reviews_dir + '/new'):
        f = os.path.join(reviews_dir + '/new', filename)

        print(filename)
        if os.path.isfile(f):
            print(f)
        with open(f) as file:
            lines = file.readlines()
            for index, line in enumerate(lines):
                print("\n")
                print("Line {}: {}".format(index, line.strip()))


def check_parsed_reviews(num, filename):
    with open(filename) as file:
        reviews_count = len(file.readlines())
    with open('../data/parsed_movies_3.csv') as movie_list:
        reader = csv.reader(movie_list)
        for row in reader:
            index, parsed_date, title, title_num, reviews_parsed, reviews_expected, diff, url = row
            print(reviews_count, reviews_parsed)
            if title_num == num:
                if reviews_count != reviews_parsed:
                    text = f"{index} Expected {reviews_parsed}/{reviews_expected} got {reviews_count}" \
                           f" diff {reviews_count - int(reviews_parsed)} title_num = {title_num} time {parsed_date} url {url}"
                    write_error_movie(text)

                    return 0
                    # with open(f) as file:
                    #     lines = file.readlines()
                    #     for i, line in enumerate(lines, start=1):
                    #         print(f"{i} {line}")
            break
    return 1


def parse_review_file():
    with open("../data/Everything Everywhere All at Once User Reviews - IMDb.html") as fp:
        soup = BeautifulSoup(fp, "html.parser")

        reviews = [x.text for x in soup.find_all("div", class_="text show-more__control")]

        pagination_key = soup.find('div', class_='load-more-data')['data-key']
        reviews_count = soup.find("div", class_="header").find("div").text
        print(reviews_count)

        with open(reviews_dir + 'test.csv', 'w') as fd:
            for review in reviews:
                fd.write(f"{review}\n")
        print(pagination_key)


class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("../logs/log_2.dat", "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self, message="None"):
        self.terminal.write(message)
        self.log.write(message)


sys.stdout = Logger()

parse_top_1000_movies_reviews()