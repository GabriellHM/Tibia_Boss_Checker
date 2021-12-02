from urllib.request import urlopen, Request
import sqlite3, time, datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By

#connecting to the sql database
sql_connection = sqlite3.connect("data.db")
cursor = sql_connection.cursor()


#getting the servers' names
def get_servers():

    #reading the webpage while circunventing primitive web scraping protection
    req = Request('https://www.tibia.com/community/?subtopic=killstatistics', headers={"User-Agent": "Mozilla/5.0"})
    html = urlopen(req).read()

    #parsing the html data
    bs = BeautifulSoup(html, "html.parser")

    #grabbing the elements <option></option>
    lines = bs.find_all('option')
    
    #getting the server names from the database
    cursor.execute("""
        SELECT * FROM servers
    """)
    server_names = [tuple[1] for tuple in cursor.fetchall()]

    #iterating over the servers found thru scrapping
    for s in lines:
        if s.text != ("(choose world)"): #ignore the (choose world) select option
            if s.text in server_names: #if the server is already in the database, ignore
                next
            else: #if it's not in the database: insert it to the database
                cursor.execute(f"""
                    INSERT INTO servers (server_name)
                    VALUES ('{s.text}')
                """)

    sql_connection.commit()

#getting the kill data
def get_creatures(server):
    start_time = time.perf_counter()
    #setting the browser options to make it "invisible"
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')

    print(f'Getting data from the server {server}...')

    #defining the web driver to load the page
    driver = webdriver.Firefox(options=options)
    driver.get('https://www.tibia.com/community/?subtopic=killstatistics')

    #waiting for the page to fully load
    time.sleep(6)

    #finding the select element and selecting the server
    select = Select(driver.find_element(By.TAG_NAME, 'select'))
    select.select_by_value(f'{server}')

    #finding the submit button and clicking on it
    driver.find_element(By.XPATH, """
        /html/body/div[4]/div[3]/div[3]/div[5]/div/div/form/div/table/tbody/tr/td/div/table/tbody/tr/td[3]/div/div/input""").click()

    #waiting for the new elements to load
    time.sleep(6)

    #getting the html for the table element
    bs = BeautifulSoup(driver.find_element(By.ID, 'KillStatisticsTable').get_attribute('innerHTML'), 'html.parser')
    
    #filtering the table lines
    tr = bs.find_all('tr')

    #table header
    table_header = ['Last Day', 'Last Week', 'Race', 'Killed Players', 'Killed by Players']

    #dict to get the date (it's always the day before today)
    data = {}
    data['date'] = datetime.datetime.strftime((datetime.datetime.now() - datetime.timedelta(days=1)), '%d/%m/%Y')

    #iterating thru the table
    exit_loop = False
    first_element = True
    for n in tr:
        if first_element == True: #skipping the first element
            first_element = False
        else:
            td = n.find_all('td') #find all <td> elements inside the <tr> element
            count = 0
            creature = 'error'
            for l in td:
                if l.text == '(elemental forces)' or l.text in table_header:  #ignoring the first table element
                    break
                elif len(l.text) > 0 and l.text[0].islower():    #cheking when table reaches regular creatures
                    exit_loop = True
                    break
                else:
                    if count == 2 and len(l.text) > 0 and int(l.text) > 0: #if the monster was killed, we overwrite(if there was already the value 0) the value to the number of kills
                        data[creature] = int(l.text)
                        break
                    elif count == 1 and len(l.text) > 0 and int(l.text) > 0: #if the monster killed players, we add it to the dict but with value 0
                        data[creature] = 0
                        break
                    elif count == 0 and len(l.text) > 0: #the first element is the creature name, which we save in a temporary variable
                        creature = l.text
                        count += 1
                    else:
                        count += 1

            if exit_loop == True:    #exiting the loop early instead of running thru regular creatures
                break
    

    #closing the browser
    driver.close()

    print(f'Done collecting data in {time.perf_counter() - start_time} s.')
    update_creatures(data)  #updating the creatures table in the database (if there's new creatures)
    update_kills(data, server) #updating the kills table in the database
    

#updating the creature table in database
def update_creatures(data):

    start_time = time.perf_counter()
    print('Updating creatures\' table...')

    #getting the list of creatures from the database
    cursor.execute("""
            SELECT creature_name FROM creatures
    """)
    
    creatures = [tuple[0] for tuple in cursor.fetchall()]
    
    #iterating over the data file checking if there is a creature that isn't in the database
    for key in data.keys():
        if key != 'date':
            if key not in creatures:
                cursor.execute("""
                        INSERT INTO creatures (creature_name)
                        VALUES (?)
                """, (key,))

    sql_connection.commit()
    print(f'Done updating in {time.perf_counter() - start_time} s.')

#updating the kills table in database
def update_kills(data, server):

    start_time = time.perf_counter()
    print('Updating kills\' table...')

    #getting the server_id
    cursor.execute("""
            SELECT id FROM servers
            WHERE server_name = ?
    """, (server,))

    t = cursor.fetchall()
    server_id = t[0][0]

    #updating the kills table
    for key in data.keys():
        if key != 'date':       #ignore the date key
            #get the creature_id
            cursor.execute("""
                    SELECT id FROM creatures
                    WHERE creature_name = ?
            """, (key,))

            t = cursor.fetchall()
            creature_id = t[0][0]

            #check if there is already a input for the creature, server and date
            cursor.execute("""
                    SELECT * FROM kills
                    WHERE server_id = ? AND creature_id = ? AND date = ?
            """, (server_id, creature_id, data['date']))
            
            # if there's nothing, then we insert the data to the table
            if len(cursor.fetchall()) == 0:

                cursor.execute("""
                        INSERT INTO kills (server_id, creature_id, date, kills)
                        VALUES (?, ?, ?, ?)
                """, (server_id, creature_id, data['date'], data[key]))

    sql_connection.commit()
    print(f'Done updating kills table in {time.perf_counter() - start_time} s')

#table creation
def create_tables():

    cursor.execute("""
        CREATE TABLE servers (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            server_name TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE creatures (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            creature_name TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE kills (
            server_id INTEGER NOT NULL,
            creature_id INTEGER NOT NULL,
            date DATE NOT NULL,
            kills INTEGER NOT NULL
        )
    """)

#deleting tables
def delete_tables():

    cursor.execute("""
        DROP TABLE creatures;
    """)
    sql_connection.commit()

#main web_scraper code
def main():
    #updating the servers table in the database
    print('Updating the servers\' table...')
    init_time = time.perf_counter()
    get_servers()  
    print(f'Servers\' table updated in {(time.perf_counter() - init_time)} s')

    #getting the list of servers from the database
    cursor.execute("""
            SELECT server_name FROM servers
    """)
    server_list = [tuple[0] for tuple in cursor.fetchall()]

    #running the web scrapper script for every server
    for server in server_list:
        start_time = time.perf_counter()
        get_creatures(server)
        print(f'All done with {server}. Took {time.perf_counter() - start_time} s.\nWaiting 15 seconds before next server...')
        time.sleep(15)

main()