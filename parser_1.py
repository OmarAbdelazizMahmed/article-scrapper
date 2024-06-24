import requests
from bs4 import BeautifulSoup
import pandas as pd
from time import sleep
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import urljoin
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define a mapping of deprecated tags to new tags
TAG_MAPPING = {
    'strike': 's',
    'u': 'span class="underline"',
    'b': 'strong',
    'i': 'em',
    'center': 'div style="text-align: center;"',
    'font': 'span',
    'big': 'span style="font-size: larger;"',
    'small': 'span style="font-size: smaller;"',
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

def replace_deprecated_tags(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for deprecated_tag, new_tag in TAG_MAPPING.items():
        for tag in soup.find_all(deprecated_tag):
            new_tag_name, _, new_tag_attrs = new_tag.partition(' ')
            tag.name = new_tag_name
            if new_tag_attrs:
                attrs = dict(attr.split('=') for attr in new_tag_attrs.split() if '=' in attr)
                tag.attrs.update(attrs)
    for tag in soup.find_all():
        # Remove attributes from all tags
        tag.attrs = {}
            
    return str(soup)

def initialize_driver():
    """Initialize and return a headless Selenium WebDriver."""
    options = Options()
    options.headless = True
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    return driver

def get_articles(domain, category_keyword, num_articles=10, selectors=None):
    articles = []
    page = 1
    driver = initialize_driver()

    while True:
        url = urljoin(domain, f"?page={page}")
        logging.info(f"Fetching URL: {url}")
        
        driver.get(url)
        sleep(2)  # Adding delay to handle dynamic content loading

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        article_elements = []
        article_selector = selectors.get('article', {})
        if article_selector['type'] == 'tag':
            article_elements = soup.find_all(article_selector['name'])
        elif article_selector['type'] == 'class':
            article_elements = soup.find_all(class_=article_selector['name'])
        else:
            logging.error(f"Unsupported selector type: {article_selector['type']}")
            continue

        if not article_elements:
            logging.info("No more articles found.")
            break

        for article in article_elements:
            try:
                if selectors['title']['type'] == 'class':
                    title_element = article.find(class_=selectors['title']['name'])
                elif selectors['title']['type'] == 'tag':
                    title_element = article.find(selectors['title']['name'])

                if not title_element:
                    logging.warning("Title element not found")
                    continue
                title = title_element.get_text(strip=True)
                link_element = article.find('a')
                if not link_element or 'href' not in link_element.attrs:
                    logging.warning("Link element not found or missing href attribute")
                    continue
                link = link_element['href']
                date_element = article.find(selectors['date']['type'], selectors['date']['name'])
                date = date_element.get_text(strip=True) if date_element else ''
    
                full_link = urljoin(domain, link)
                logging.info(f"Visiting article URL: {full_link}")
                driver.get(full_link)
                sleep(2)  # Adding delay to handle dynamic content loading
                article_soup = BeautifulSoup(driver.page_source, 'html.parser')

                content_element = article_soup.find(class_=re.compile(".*content.*"))
                content = content_element.encode_contents() if content_element else ''

                if re.search(re.escape(category_keyword).replace('\\*', '.*'), full_link, re.IGNORECASE) \
                        or re.search(re.escape(category_keyword).replace('\\*', '.*'), title, re.IGNORECASE):
                    articles.append({
                        'title': title,
                        'link': full_link,
                        'date': date,
                        'content': replace_deprecated_tags(content.decode())
                    })

                if len(articles) >= num_articles:
                    break
            except AttributeError as e:
                logging.error(f"Error processing article: {e}")

        if len(articles) >= num_articles:
            break

        page += 1
        sleep(1)

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

# Usage example
domain = "https://www.freelancer.com/community/freelancing"
category_keyword = "freelance"
selectors = {
    'article': {
        'type': 'tag',
        'name': 'article',
    },
    'title': {
        'type': 'tag',
        'name': 'h3',
    },
    'date': {
        'type': 'class',
        'name': 'article-date'
    },
    'content': {
        'type': 'class',
        'name': 'article-content'
    }
}
articles = get_articles(domain, category_keyword, num_articles=10, selectors=selectors)
# save_to_excel(articles, "articles.xlsx")
save_to_csv(articles, "articles.csv")
