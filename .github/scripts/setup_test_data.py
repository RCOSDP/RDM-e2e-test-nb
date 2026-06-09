from django.utils import timezone
from osf.models import OSFUser, Node, Institution

INSTITUTION_NAME = 'Virginia Tech [Test]'

test_users = [
    {
        'username': 'testuser1@example.com',
        'fullname': 'Test User 1',
        'given_name': 'Test',
        'family_name': 'User 1',
        'given_name_ja': 'テスト',
        'family_name_ja': 'ユーザー1',
        'password': 'testpass123',
        'is_superuser': True,
    },
    {
        'username': 'testuser2@example.com',
        'fullname': 'Test User 2',
        'given_name': 'Test',
        'family_name': 'User 2',
        'given_name_ja': 'テスト',
        'family_name_ja': 'ユーザー2',
        'password': 'testpass456',
    },
    {
        'username': 'teststaff@example.com',
        'fullname': 'Test Staff',
        'given_name': 'Test',
        'family_name': 'Staff',
        'given_name_ja': 'テスト',
        'family_name_ja': 'スタッフ',
        'password': 'testpass789',
        'is_staff': True,
    },
    {
        'username': 'testuser3@example.com',
        'fullname': 'Test User 3',
        'given_name': 'Test',
        'family_name': 'User 3',
        'given_name_ja': 'テスト',
        'family_name_ja': 'ユーザー3',
        'password': 'testpass321',
        'institution': 'Massachusetts Institute of Technology [Test]',
    },
    {
        'username': 'testuser4@example.com',
        'fullname': 'Test User 4',
        'given_name': 'Test',
        'family_name': 'User 4',
        'given_name_ja': 'テスト',
        'family_name_ja': 'ユーザー4',
        'password': 'testpass654',
        'institution': 'Massachusetts Institute of Technology [Test]',
        'skip_project': True,  # Dedicated user for project limit tests; no pre-created project
    },
    {
        'username': 'testuser5@example.com',
        'fullname': 'Test User 5',
        'given_name': 'Test',
        'family_name': 'User 5',
        'given_name_ja': 'テスト',
        'family_name_ja': 'ユーザー5',
        'password': 'testpass987',
        'institution': 'Massachusetts Institute of Technology [Test]',
        'skip_project': True,  # Dedicated user for project limit tests; no pre-created project
    },
]

for user_data in test_users:
    username = user_data['username']
    if not OSFUser.objects.filter(username=username).exists():
        # Create user manually instead of using create_user
        user = OSFUser(
            username=username,
            fullname=user_data['fullname'],
            given_name=user_data['given_name'],
            family_name=user_data['family_name'],
            given_name_ja=user_data['given_name_ja'],
            family_name_ja=user_data['family_name_ja'],
            is_active=True,
            date_registered=timezone.now()
        )
        user.set_password(user_data['password'])
        user.save()
        # Set additional fields after save
        user.is_registered = True
        user.date_confirmed = timezone.now()
        user.have_email = True
        # Set jobs for profile completion (required for is_full_account_required_info)
        # Structure must match unserialize_job in website/profile/views.py
        user_institution = user_data.get('institution', INSTITUTION_NAME)
        user.jobs = [{
            'institution': user_institution,
            'department': None,
            'institution_ja': user_institution,
            'department_ja': None,
            'title': None,
            'startMonth': None,
            'startYear': None,
            'endMonth': None,
            'endYear': None,
            'ongoing': None,
        }]
        # Set superuser if specified
        if user_data.get('is_superuser', False):
            user.is_superuser = True
            user.is_staff = True
        # Set staff if specified (without superuser)
        elif user_data.get('is_staff', False):
            user.is_staff = True
        user.save()
        
        # Create email for the user
        user.emails.create(address=username)
        print(f"Created test user: {username}")
        
        # Skip project creation for dedicated CI users (e.g. project limit test user)
        if user_data.get('skip_project', False):
            print(f"Skipping project creation for {username} (skip_project=True)")
        else:
            # Create a project for the new user
            project = Node(
                title=f"Test Project for {user_data['fullname']}",
                creator=user,
                category="project",
                is_public=False
            )
            project.save()
            print(f"Created test project: {project._id} for user: {username}")
            # Output for CI config
            print(f"PROJECT_ID_{username}: {project._id}")
            print(f"PROJECT_NAME_{username}: {project.title}")
    else:
        print(f"Test user already exists: {username}")
        # Skip project check for dedicated users that should not have projects
        if user_data.get('skip_project', False):
            print(f"Skipping project creation for {username} (skip_project=True)")
        else:
            # Ensure existing user has at least one project
            user = OSFUser.objects.get(username=username)
            if not user.nodes.filter(category='project').exists():
                project = Node(
                    title=f"Test Project for {user.fullname}",
                    creator=user,
                    category="project",
                    is_public=False
                )
                project.save()
                print(f"Created test project: {project._id} for existing user: {username}")
            else:
                project = user.nodes.filter(category='project').first()
            # Output for CI config
            print(f"PROJECT_ID_{username}: {project._id}")
            print(f"PROJECT_NAME_{username}: {project.title}")

# Affiliate users with institution
for user_data in test_users:
    user = OSFUser.objects.get(username=user_data['username'])
    user_institution = user_data.get('institution', INSTITUTION_NAME)
    inst = Institution.objects.get(name=user_institution)
    if inst not in user.affiliated_institutions.all():
        user.affiliated_institutions.add(inst)
        user.save()
        print(f"Affiliated {user.username} with {inst.name}")
    else:
        print(f"User {user.username} already affiliated with {inst.name}")
