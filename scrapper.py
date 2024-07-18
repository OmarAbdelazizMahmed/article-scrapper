import requests
from bs4 import BeautifulSoup, Comment
import pandas as pd
from time import sleep
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin
import re

# Constants and configurations
DOMAIN = "https://www.freelancer.com/community/freelancing"
CATEGORY_KEYWORD = "freelance"
NUM_ARTICLES = 10
SELECTORS = {
    'article': {'type': 'tag', 'name': 'article'},
    'title': {'type': 'tag', 'name': 'h3'},
    'date': {'type': 'class', 'name': 'article-date'},
    'content': {'type': 'class', 'name': 'article-content'}
}

LOGGING_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT)

TAG_MAPPING = {
    'strike': 's',
    'u': 'span class="underline"',
    'b': 'strong',
    'i': 'em',
    'center': 'div style="text-align: center;"',
    'font': 'span',
    'big': 'span style="font-size: larger;"',
    'tt': 'code',
    'abbr': 'span class="abbr"',
    'acronym': 'span class="acronym"',
    'dir': 'ul',
    'menu': 'ul',
    'applet': 'object',
    'basefont': 'span',
    'frame': 'iframe',
    'frameset': 'iframe',
    'noframes': 'iframe',
    'xmp': 'pre',
    'plaintext': 'pre',
    'h1': 'h2',
    'h3': 'h2',
    'h4': 'h2',
    'h5': 'h2',
    'h6': 'h2',
}

ALLOWED_TAGS = ['div', 'article', 'p', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'small', 'a', 'button']

def replace_deprecated_tags(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))
    for comment in comments:
        comment.extract()
    for script in soup.find_all('script'):
        script.extract()
    for style_tag in soup.find_all('style'):
        style_text = style_tag.get_text()
        if 'webapp-compat-navigation:not(.WebappCompatPlaceholder)' in style_text \
                or 'webapp-compat-navigation-empty:not(.WebappCompatPlaceholder)' in style_text \
                or 'webapp-compat-seo-navbar.WebappCompatPlaceholder' in style_text \
                or 'app-seo-navbar' in style_text:
            style_tag.extract()
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            if tag.name in TAG_MAPPING:
                new_tag = TAG_MAPPING[tag.name]
                if new_tag.startswith('<'):
                    new_tag = BeautifulSoup(new_tag, 'html.parser').find()
                    tag.replace_with(new_tag)
                else:
                    tag.name = new_tag
            else:
                tag.unwrap()
        else:
            tag.attrs = {}  # Remove all attributes from allowed tags
    return str(soup)

def extract_text_with_html(article_soup):
    body_tag = article_soup.find('body')
    return str(body_tag) if body_tag else ""

def initialize_driver():
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

def extract_article_data(article, selectors):
    title_element = article.find(class_=selectors['title']['name']) if selectors['title']['type'] == 'class' else article.find(selectors['title']['name'])
    title = title_element.get_text(strip=True) if title_element else None

    link_element = article.find('a')
    link = link_element['href'] if link_element and 'href' in link_element.attrs else None

    date_element = article.find(selectors['date']['type'], selectors['date']['name'])
    date = date_element.get_text(strip=True) if date_element else ''

    return title, link, date

def fetch_articles(driver, domain, page, selectors):
    url = urljoin(domain, f"?page={page}")
    logging.info(f"Fetching URL: {url}")
    driver.get(url)
    sleep(2)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    article_elements = soup.find_all(selectors['article']['name']) if selectors['article']['type'] == 'tag' else soup.find_all(class_=selectors['article']['name'])

    return article_elements

def process_article(driver, domain, article, selectors, category_keyword):
    try:
        title, link, date = extract_article_data(article, selectors)
        if not title or not link:
            logging.warning("Missing title or link, skipping article")
            return None

        full_link = urljoin(domain, link)
        logging.info(f"Visiting article URL: {full_link}")
        driver.get(full_link)
        sleep(2)
        article_soup = BeautifulSoup(driver.page_source, 'html.parser')

        content_with_html = extract_text_with_html(article_soup)
        content = replace_deprecated_tags(content_with_html)

        if re.search(re.escape(category_keyword).replace('\\*', '.*'), full_link, re.IGNORECASE) \
                or re.search(re.escape(category_keyword).replace('\\*', '.*'), title, re.IGNORECASE):
            return {'title': title, 'link': full_link, 'date': date, 'content': content, 'content_with_html': content_with_html}
    except AttributeError as e:
        logging.error(f"Error processing article: {e}")
    return None

def get_articles(domain, category_keyword, num_articles, selectors):
    articles = []
    page = 1
    driver = initialize_driver()

    try:
        while len(articles) < num_articles:
            article_elements = fetch_articles(driver, domain, page, selectors)
            if not article_elements:
                logging.info("No more articles found.")
                break

            for article in article_elements:
                article_data = process_article(driver, domain, article, selectors, category_keyword)
                if article_data:
                    articles.append(article_data)
                    if len(articles) >= num_articles:
                        break

            page += 1
            sleep(1)
    finally:
        driver.quit()

    return articles

def save_to_excel(articles, filename):
    df = pd.DataFrame(articles)
    df.to_excel(filename, index=False)
    logging.info(f"Data saved to {filename}")

def save_to_csv(articles, filename):
    df = pd.DataFrame(articles)
    df.to_csv(filename, index=False)
    logging.info(f"Data saved to {filename}")

if __name__ == "__main__":
    articles = get_articles(DOMAIN, CATEGORY_KEYWORD, NUM_ARTICLES, SELECTORS)
    save_to_csv(articles, "articles.csv")
    # save_to_excel(articles, "articles.xlsx")
