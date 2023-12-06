from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import openai
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import json
import pytz
import datetime
import icalendar
from icalendar import Calendar
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError



client = OpenAI()
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes



def split_list(arr, num_per_arr=50):
    """
    Function that splits a list into a list of lists. Each list caps out at
    num_per_arr elements. This is for ChatGPT parsing purposes. First element in
    arr_split has the first num_per_arr elements of arr, second element has the
    next num_per_arr, etc.
    """
    arr_split = []

    # Splitting the list into chunks of 50 elements each
    for i in range(0, len(arr), num_per_arr):
        arr_split.append(arr[i : i + num_per_arr])

    return arr_split




def query_chatgpt(system_instructions, prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def assign_tags(event_list):
    """
    Takes in a list of event names. Returns a list of dictionaries.
    Each dictionary has attribute "name" with just the event name
    and "tag" which is the ChatGPT generated tag.
    """
    event_list_tagged = []
    event_list_split = split_list(event_list)

    for arr in event_list_split:
        system_instructions = "Take a Python list of event names as input. For every event in the list, create a tag that describes the academic subject, activity, or theme of the event. Suitable tags are, for example: programming, CS, biology, science, career, entrepreneurship, social, charity, etc. Do not include redundant words like: recitation, lecture, activity, etc. Return a Python list of all the tags."
        prompt = str(arr)

        response = query_chatgpt(system_instructions, prompt)
        response_split = response.split()
        response_corrected = []
        for word in response_split:
            response_corrected.append("".join(char for char in word if char.isalpha()))

        print(response_corrected)

        for i in range(min(len(arr), len(response_corrected))):
            event_list_tagged.append({"name": arr[i], "tags": response_corrected[i]})

    return event_list_tagged


def assign_fixed_tags(event_list):
    """
    Takes in a list of event names. Returns a list of tags.
    Each tag is in a list of fixed tags. ChatGPT is forced
    to select a tag for the event outside the fixed list.
    """

    tag_list = []
    event_list_split = split_list(event_list)
    fixed_tag_list = ["computer science","entrepreneurship","arts","social","health","diversity","sustainability","career","religious","chemistry","music","hobbies","business","food","travel"]

    for arr in event_list_split:
        system_instructions = f"Take a Python list of event names as input. For every event in the list, choose a tag from {fixed_tag_list}. Return a Python list of all the tags. Do not include any text other than the Python list."
        prompt = str(arr)

        response = query_chatgpt(system_instructions, prompt)
        response_split = response.split(",")
        response_corrected = []
        for word in response_split:
            response_corrected.append("".join(char for char in word if char.isalpha()))

        for i in range(min(len(arr), len(response_corrected))):
            tag_list.append({"name": arr[i], "tags": response_corrected[i]})

    return tag_list


def count_tag_apperances(events_with_tags):
    """
    Counts the number of instances that a given tuple of tags occurs.
    Takes in a list of tagged events as input. Returns a dictionary mapping the
    tag tuples to their counts.
    """

    tag_dict = {}

    for event in events_with_tags:
        tags = tuple(event["tags"])
        if tags not in tag_dict:
            tag_dict[tags] = 1
        else:
            tag_dict[tags] += 1

    return tag_dict


def match_gcal_to_events(cal_events, mit_events):
    """
    Takes two lists of calendar events and mit events as input. Uses GPT to analyze the
    calendar events to figure out sets of tags that you like. Matches them with mit
    events that fit the corresponding tags.
    """
    def join_tuple(the_tuple):
        result = ""
        for char in the_tuple:
            result = result + char
        return result
        # result = ""
        # for char in the_tuple:
        #   result = result + char

        # return result

    mit_event_names = [event["name"] for event in mit_events]
    mit_event_names_split = split_list(mit_event_names)

    calendar_tag_apperances = count_tag_apperances(assign_fixed_tags(cal_events))
    sorted_dict = sorted(
        calendar_tag_apperances.items(), key=lambda x: x[1], reverse=True
    )
    top_keys = [join_tuple(key) for key, value in sorted_dict[:3]]

    top_key_occurrences = [0, 0, 0]
    top_events = []
    print(top_keys)
    fixed_tag_list = ["computer science","entrepreneurship","arts","social","health","diversity","sustainability","career","religious","chemistry","music","hobbies","business","food","travel"]

    for i in range(len(mit_event_names)):
        event_name = mit_event_names[i]
        system_instructions = f"Take an event name as input. Choose a tag for the event from {fixed_tag_list}. Do not include any text other than the tag."
        prompt = str(event_name)
        response = query_chatgpt(system_instructions, prompt)
        response_stripped = response.replace(" ", "")
        print(response_stripped)

        if response_stripped == top_keys[0] and top_key_occurrences[0] < 3:
            top_key_occurrences[0] += 1
            top_events.append(mit_events[i])
        elif response_stripped == top_keys[1] and top_key_occurrences[1] < 2:
            top_key_occurrences[1] += 1
            top_events.append(mit_events[i])
        elif response_stripped == top_keys[2] and top_key_occurrences[2] < 1:
            top_key_occurrences[2] += 1
            top_events.append(mit_events[i])
        # if top_key_occurrences[0] == 3 and top_key_occurrences[1] == 2 and top_key_occurrences[2] == 1:
        #     break

        if i > 100 or (top_key_occurrences[0] == 3 and top_key_occurrences[1] == 2 and top_key_occurrences[2] == 1):
            break

    return top_events

def scrape_single_MIT_url(url):
    """
    Takes a single url off of calendar.mit.edu and scrapes the events.
    Returns a list of dictionaries, where key "name" returns the big bold name,
    key "description" returns the description of the event, and key "location"
    returns the location of the event.
    """
    get_webpage = requests.get(url)
    soup = BeautifulSoup(get_webpage.content, "html.parser")
    current_time = datetime.now()
    current_time = current_time.replace(tzinfo=pytz.UTC)

    events = []
    for event in soup.find_all("div", class_="item event_item vevent"):
        # print("THE FOLLOWING IS AN EVENT \nTHE FOLLOWING IS AN EVENT \n")
        # print(event)
        time_details = event.find("div", class_="dateright")

        event_details = {
            "name": event.find("h3", class_="summary").text.strip(),
            "description": event.find("h4", class_="description").text.strip(),
            "location": event.find("div", class_="location").text.strip(),
            "is_rigword": False,
        }

        if event_details["location"] == "":
            event_details["location"] = None


        if time_details.find("abbr", class_="dtstart") is None:
            event_details["start"] = None
        elif datetime.fromisoformat(time_details.find("abbr", class_="dtstart").get("title").strip()) < current_time:
            continue
        else:
            event_details["start"] = (
                time_details.find("abbr", class_="dtstart").get("title").strip()
            )

        if time_details.find("abbr", class_="dtend") is None:
            event_details["end"] = None
        else:
            time_end = time_details.find("abbr", class_="dtend").get("title").strip()
            if time_end in (None, ""):
                event_details["end"] = None
            else:
                event_details["end"] = time_end

        events.append(event_details)

    return events


def scrape_MIT_year(year_number):
    """
    Scrapes a full given year of MIT events off calendar.mit.edu.
    Returns a list of dictionaries as described in scrape_single_MIT_url.
    """
    url = "https://calendar.mit.edu/calendar/month/" + str(year_number) + "/"
    events = []

    for month_number in range(1, 13):
        events += scrape_single_MIT_url(url + str(month_number))

    return events

def parse_calendar(file_path, date_tuple=(2000, 1, 1), duplicate_repeat_events=False):
    """
    Returns a dictionary of event names and event descriptions scraped off the
    .ics calendar file.
    """

    # creates a usable date object
    after_date = datetime(date_tuple[0], date_tuple[1], date_tuple[2], 0, 0, 0)
    after_date = after_date.replace(tzinfo=pytz.UTC)

    with open(file_path, "rb") as ics_file:
        calendar = Calendar.from_ical(ics_file.read())
        # idk how this works but it's part of the icalendar library so whatever

    calendar_event_list = []

    for component in calendar.walk():
        if component.name == "VEVENT":
            event_start = component.get("dtstart").dt
            if not isinstance(event_start, datetime):
                event_start = datetime.combine(event_start, datetime.min.time())
                event_start = event_start.replace(tzinfo=pytz.UTC)
            # gets start date/time of the event

            if event_start > after_date:
                event_name = component.get("SUMMARY")
                does_event_repeat = component.get("RRULE")

                if duplicate_repeat_events and does_event_repeat:
                    for _ in range(duplicate_repeat_events):
                        # calendar_event_list.append(
                        #     {
                        #         "name": event_name,
                        #         "description": event_name,
                        #     }
                        # )

                        calendar_event_list.append(event_name)
                else:
                    # calendar_event_list.append(
                    #     {
                    #         "name": event_name,
                    #         "description": event_name,
                    #     }
                    # )
                    calendar_event_list.append(event_name)

    return calendar_event_list

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def convert_event_format(email, internal_event_repr):
    """
    Converts an event in our internal representation of the tagged datasets into
    a format that can get inputted into the GCal event creation. Does not mutate
    the original.
    """
    assert internal_event_repr["is_rigword"] is False

    calendar_event = {
        "summary": internal_event_repr["name"],
        "description": internal_event_repr["description"],
        "attendees": [
            {"email": email},
        ],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 10},
            ],
        },
    }

    # if the end time is None, then we just make it an all day event.
    if internal_event_repr["end"] is None:
        # To do this, we extract the date from start_time, and make the event
        # start and end both a date. (this is how to create full day events)
        # ['start'] is still a dict, but a single element dict containing only
        # a 'dict' key
        event_date = (internal_event_repr["start"].split("T"))[0]
        calendar_event["start"] = {"date": event_date}
        calendar_event["end"] = {"date": event_date}
    else:
        calendar_event["start"] = {
            "dateTime": internal_event_repr["start"],
            "timeZone": "America/New_York",
        }
        calendar_event["end"] = {
            "dateTime": internal_event_repr["end"],
            "timeZone": "America/New_York",
        }

    if internal_event_repr["location"] is not None:
        calendar_event["location"] = internal_event_repr["location"]

    return calendar_event


def create_event_and_invite_user(email, internal_event_repr):
    """Shows basic usage of the Google Calendar API.
    Creates an event and sends an email to the indicated recipient.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)

        # Call the Calendar API
        event = convert_event_format(email, internal_event_repr)
        event = service.events().insert(calendarId='primary', sendNotifications=True, body=event).execute()
        # event = (
        #     service.events()
        #     .insert(calendarId="primary", sendNotifications=True, body=event)
        #     .execute()
        # )
        print("Event created: %s" % (event.get("htmlLink")))

    except HttpError as error:
        print(f"An error occurred: {error}")

# events_december_2023 = scrape_single_MIT_url("https://calendar.mit.edu/calendar/month/2023/12")
# sam_calendar = parse_calendar("samueltzhou@gmail.com.ics", (2023, 6, 1))

# print("scraping done")

# for event in match_gcal_to_events(sam_calendar, events_december_2023):
#     # create_event_and_invite_user("starfarmcraft@gmail.com", event)
#     print("The next event is:", event['name'])
#     inp_string = input("Would you like to add this event to your calendar? Enter Y if you would like to and N otherwise.")
#     while not (inp_string.strip().lower() == "y" or inp_string.strip().lower() == "n"):
#         inp_string = input("Please enter either Y or N.")

#     if inp_string.strip().lower() == "y":
#         print("Creating event:")
#         create_event_and_invite_user("starfarmcraft@gmail.com", event)
#     elif inp_string.strip().lower() == "n":
#         print("Event skipped, moving on.")

@app.route('/hello-world', methods=['GET'])
def hello_world():
    return jsonify({'text': "hello world"})

@app.route('/process-text', methods=['POST'])
def process_text():
    if not request.json or 'text' not in request.json: # Check if text is sent via JSON
        return jsonify({'error': 'No text provided'}), 400

    events_december_2023 = scrape_single_MIT_url("https://calendar.mit.edu/calendar/month/2023/12")
    sam_calendar = parse_calendar("samueltzhou@gmail.com.ics", (2023, 6, 1))

    matched_events = match_gcal_to_events(sam_calendar, events_december_2023)

    text = "The following events have been added to your calendar:\n"
    for event in matched_events:
        create_event_and_invite_user("starfarmcraft@gmail.com", event)
        text = text + event['name'] + "\n"

    # for event in events_december_2023:
    #     text = text + event['name'] + "\n"

    return jsonify({'text': text})    


# def process_text():
#     if not request.json or 'text' not in request.json: # Check if text is sent via JSON
#         return jsonify({'error': 'No text provided'}), 400
#     text = request.json['text']
#     processed_text = text.upper()  # Convert text to uppercase
#     return jsonify({'text': processed_text})






if __name__ == '__main__':
    app.run(debug=True)