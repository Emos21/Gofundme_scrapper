from bs4 import BeautifulSoup
import requests
import csv

page_to_scrape = requests.get("https://www.consumeraffairs.com")
soup = BeautifulSoup(page_to_scrape.text, "html.parser")
reviews = soup.findAll("p", attrs={"class":""})
authors = soup.findAll("span", attrs={"class":"rvw__inf-nm"})

file = open("consumeraffairs.csv", "w")
writer = csv.writer(file)

writer.writerow(["Reviews", "Authors"])


for review, author in zip(reviews, authors):
    # print(review.text + " - " + author.text)
    writer.writerow([review.text, author.text])
file.close()
