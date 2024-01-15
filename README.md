# Comparator for anilist and myanimelist lists.
## What is it
Simple application for comparing anime lists from both services.
Uses flask as a base with sqllite as its database.

## Possible pages
- /add_user : Adding a user does create a user in the database as well as creates an entry for every distinct Anime not in database. Looks only at completed shows.
- /compare : Comparing between two lists returns a collage of pictures based on scores.
- /tables : Given selection of users within this page returns table of unique anime and users scores 
- /reload_all : Reloads all users within the database.

### Yes the site itself isn't so pretty however it does its job. 