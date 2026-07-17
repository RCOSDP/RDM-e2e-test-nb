import os
from django.utils import timezone
from osf.models import OSFUser, Node, Institution

WIKI_ENABLED = os.environ.get('WIKI_ENABLED', 'false').lower() == 'true'

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
]

def create_rdmuserkey(user):
    # このスクリプトは `manage.py shell < file` で exec されるため、
    # 関数内で使うシンボルは関数内で import する（トップレベル import は関数から見えない）
    import hashlib
    from django.utils import timezone
    from osf.models.rdm_user_key import RdmUserKey

    PRIVATE_KEY_VALUE = 1
    PUBLIC_KEY_VALUE = 2

    if RdmUserKey.objects.filter(guid=user.id).exists():
        print(f"RdmUserKey already exists for user: {user.username}")
        return
    
    now = timezone.now()
    date_hash = hashlib.md5(now.strftime('%Y%m%d%H%M%S').encode('utf-8')).hexdigest()
    pvt_key_name = f'{user._id}_{date_hash}_pvt.pem'
    pub_key_name = f'{user._id}_{date_hash}_pub.pem'

    pvt_key = RdmUserKey()
    pvt_key.guid = user.id
    pvt_key.key_name = pvt_key_name
    pvt_key.key_kind = PRIVATE_KEY_VALUE
    pvt_key.created_time = now
    pvt_key.save()

    pub_key = RdmUserKey()
    pub_key.guid = user.id
    pub_key.key_name = pub_key_name
    pub_key.key_kind = PUBLIC_KEY_VALUE
    pub_key.created_time = now
    pub_key.save()

    print(f"Created RdmUserKey (pvt+pub) for user: {user.username}")


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
        
        # Create user key (only needed when Wiki is enabled)
        if WIKI_ENABLED:
            create_rdmuserkey(user)

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
        # Ensure existing user has at least one project
        user = OSFUser.objects.get(username=username)

        # Create user key (only needed when Wiki is enabled)
        if WIKI_ENABLED:
            create_rdmuserkey(user)

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
