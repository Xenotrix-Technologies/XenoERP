import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from crm.models import Organization, UserProfile, Lead, Activity, Task, Meeting

class Command(BaseCommand):
    help = 'Seeds XenoCRM database with realistic SaaS template data.'

    def handle(self, *args, **options):
        self.stdout.write('Deleting existing data...')
        Lead.objects.all().delete()
        UserProfile.objects.all().delete()
        Organization.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Meeting.objects.all().delete()

        self.stdout.write('Creating organization...')
        org = Organization.objects.create(name="Xenotrix Technologies")

        self.stdout.write('Creating users and profiles...')
        # Create users
        users_data = [
            {
                'username': 'alex_stratton',
                'first_name': 'Alex',
                'last_name': 'Stratton',
                'role': 'CEO & Founder',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuB05rGE9-Jratkpq-Tp16RBQseAklBh_S_mxswd-xWxxFsWqJAz2gP0uL27Wjpm-GOvd0X1Ee8B0Dy6xpevKX43OCPWmsYaZ-FrIbFkcf-EVYlSGW31ePk6zCpecRKQCCdqns4nRmZHs2-lbaE7WuskZM4QBi4wusd31Yci1mmUPHBbA4A_t2xEKE8086bTIJdp3ZyG7FMdeCy5aDXiOYnyV5-8R_4zxmOSAvFgCaAfrlX2ecJU7gkMr13SxAP0CcByOgVrzp6QiBF5'
            },
            {
                'username': 'alex_rivera',
                'first_name': 'Alex',
                'last_name': 'Rivera',
                'role': 'Sales Lead',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuDzmt55HWirFDWZenkbuGP6gn8UwnBClM17H0oyHB80g8EJ_TTKcwNv5uJag-bg8_azKx4eIIk_4G7IGS5T0se2YlVy7w2yRO_evbqgK8gb7NW7EtKEApykq6bjOg4VPoZIB3U_b55JBngyuKJLL0as06l2e3rgC8MupjutRyS_JsNfjx0lguXGZaTLrHJL7Im4r598TrrzslnFJLlwUTLI6AjZLGP8ogN-a1w0ZF8EN2MkTdYsF9Ht_vTpQfgOeQEOHrkKKH8YqOB-'
            },
            {
                'username': 'sarah_chen',
                'first_name': 'Sarah',
                'last_name': 'Chen',
                'role': 'Sales Specialist',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBPJl_M-09Hxj0qEIUOe_Y0bL4-xQ2bjB_9xHxrQicegKAxvu0IoSNONZOCUuF2Vje5qP7s2KSk-zphaLB59CVaQwnao5RnZ1wlIn4ahzvMLG303Ug15--3XN7j1DdBjHQCi6_7ltmcWiaeMg2v4vWNYqLrma9Qrmn0aUroSmwjKKoHLqU5XtkG3T7_PUbh1kPER7VLMqVGs2u79sXgQejOiaQyVYIy6iFM5pt_94LUhP1gukH3k_tOMXFKRlfW3ltpgJ-eVYJrkxLY'
            },
            {
                'username': 'jordan_smith',
                'first_name': 'Jordan',
                'last_name': 'Smith',
                'role': 'Sales Representative',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBTVKaz3XpgtAEsUHbkm8-QZ5PhTku5_MpwdIJ5ZkbgVUDxd-wPb7N9XJD56fK1py3SZshrHD-Gz4myA-EcDGXtpo22_Fd4HdeVxfBK5dvKiz2Xdo2MgEdE6oRT4IW64z0u8OlzJjt-VIMQCfC8Stoa19CcbdPMOmSwyWb5J2eVR_Si_SK3tgZFDCbYosJjbgkxl2_kqu8YUxFZarBKoKqgNIYPXiTd02XJC7XI58RTMJa13kJAdJgfWuREPsLoO6wkmOJz1t_pmgeS'
            }
        ]

        profiles = {}
        for ud in users_data:
            user = User.objects.create_user(
                username=ud['username'],
                email=f"{ud['username']}@xenocrm.com",
                password='password123',
                first_name=ud['first_name'],
                last_name=ud['last_name']
            )
            profile = UserProfile.objects.create(
                user=user,
                organization=org,
                role=ud['role'],
                profile_image_url=ud['avatar']
            )
            profiles[ud['username']] = profile

        self.stdout.write('Creating leads...')
        # Leads dataset matching the Stitch mockups
        leads_data = [
            {
                'name': 'Marcus Holloway',
                'email': 'marcus.h@techvision.io',
                'company': 'TechVision Systems',
                'score': 94,
                'status': 'Qualified',
                'stage': 'Qualified',
                'value': 45000,
                'owner': 'alex_rivera',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBnVG0xiy-kPV0wqn8mDe195-ymxbyWR0eyncx3IFzrsbQfwnerlzxqtV6VT1EXra-lVceTduhTYCE5mP_KkuOFXDhrHLq9W3QtlwUrb6VSW8m--vDTQt8zyIMOEXA-bG-brz4GUaHUhMQqfoLb9IXsbXLepWF6WwHmuoaNTbYKf504357F2zxOYWRAlaZAgCeQglc6bLfXd9bvUtACA1fBYoETDbuOzjdTIM2VdGywoeoGBftWOIC5T_Ip2CygxCNWb4WJJ13Yh_jk',
                'lifecycle': 'Qualified Lead',
                'health': 85,
                'revenue': 45000
            },
            {
                'name': 'Elena Rodriguez',
                'email': 'elena.r@globalflow.com',
                'company': 'GlobalFlow Inc.',
                'score': 78,
                'status': 'Contacted',
                'stage': 'Proposal',
                'value': 12500,
                'owner': 'sarah_chen',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBPJl_M-09Hxj0qEIUOe_Y0bL4-xQ2bjB_9xHxrQicegKAxvu0IoSNONZOCUuF2Vje5qP7s2KSk-zphaLB59CVaQwnao5RnZ1wlIn4ahzvMLG303Ug15--3XN7j1DdBjHQCi6_7ltmcWiaeMg2v4vWNYqLrma9Qrmn0aUroSmwjKKoHLqU5XtkG3T7_PUbh1kPER7VLMqVGs2u79sXgQejOiaQyVYIy6iFM5pt_94LUhP1gukH3k_tOMXFKRlfW3ltpgJ-eVYJrkxLY',
                'lifecycle': 'Prospect',
                'health': 72,
                'revenue': 12500
            },
            {
                'name': 'Julian Vance',
                'email': 'j.vance@stellar-media.com',
                'company': 'Stellar Media Group',
                'score': 88,
                'status': 'New',
                'stage': 'New',
                'value': 8200,
                'owner': 'alex_rivera',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuAMzNydZylAuMJV7RxIHx9d05E0SHkLQDGLiawqAwhftqrwu2v87lASf6hTX888DMjvOngT0U2r4z2AxHY92SKjiimRfS96c0zgli6R5VubZOpY_-VXXmrJF4yADm0Uae0WT0PSzdnFHNk9_qxRVPhbijRq29GFH37ynoF5GYzl0Okes2F78ofU20ccwYSrmXIwtNwVP3lib1wIZEegLsQeAxEyNZyIp66RLhVTvjQU9lgFhGoGl8YIsK5ru2FSerRWzrfrO_lQnfC_',
                'lifecycle': 'Prospect',
                'health': 80,
                'revenue': 8200
            },
            {
                'name': 'Sophie Laurent',
                'email': 'sophie@lumina-designs.fr',
                'company': 'Lumina Designs',
                'score': 42,
                'status': 'Cold Lead',
                'stage': 'Lost',
                'value': 3400,
                'owner': 'jordan_smith',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBMKR7tQwz21dZvpmdg65eUA3EwAiKvPffN3Iizl56Frc33FRY8cXUKRpkjniJ1dSsRV_VFWWTG7R7sUUYYk6rfggrAlFsChx_HlYhdG7l0ud8xLu4Xy_7LgXdpc82ibcsmX3v2wBMrT5McISGJ_5lzHg4T6jv62z9SNoXrSsc7o9nsZ9Eao7H7_hC51oTIJySI2p5sujWVdYF84AensW7pFHeVDzHTFB_QMentHNKwsupr6cNuaHK8nhtKmrAOdzKS0iyrAcSNaisg',
                'lifecycle': 'Cold Lead',
                'health': 30,
                'revenue': 3400
            },
            {
                'name': 'Sarah Jenkins',
                'email': 'sarah@hyperscale.com',
                'company': 'HyperScale Systems',
                'score': 88,
                'status': 'Qualified',
                'stage': 'Won',
                'value': 2400000,
                'owner': 'alex_rivera',
                'avatar': 'https://lh3.googleusercontent.com/aida-public/AB6AXuBGSmkZPJzI-pQZPJ17BpGoL5CPecf9cAI8qW7jc1rnVya1c3mk1jVYPM-Y_dhcvq6QX9UAXnycfuNTJOpdKWRTyUN8kkdWU1yrdBN449m6nPiRTffghilhMpPtAyNTOEGfuxQBRAlhurpRWZm5qpGJTgcAec7qUABhoi6d5X0-QEuIaf0GG5XC6CI_YUw6FV1vzWXW2wGdkNZal8lYlZwD8I8zl1htUdfbBgvJU1VWhbkVbulHOMqNlvD4lG6sokOjw3MqqBdEiVfD',
                'lifecycle': 'Customer (Renewal due)',
                'health': 92,
                'revenue': 2400000
            },
            {
                'name': 'Global Expansion Phase 1',
                'email': 'contact@atlascorp.com',
                'company': 'Atlas Corp',
                'score': 65,
                'status': 'New',
                'stage': 'New',
                'value': 125000,
                'owner': 'sarah_chen',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 60,
                'revenue': 125000
            },
            {
                'name': 'Cloud Migration Suite',
                'email': 'it@nebulasystems.com',
                'company': 'Nebula Systems',
                'score': 85,
                'status': 'Contacted',
                'stage': 'New',
                'value': 85000,
                'owner': 'jordan_smith',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 78,
                'revenue': 85000
            },
            {
                'name': 'Security Audit Enterprise',
                'email': 'security@fortress.com',
                'company': 'Fortress Ltd',
                'score': 75,
                'status': 'Qualified',
                'stage': 'Qualified',
                'value': 210000,
                'owner': 'alex_rivera',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 80,
                'revenue': 210000
            },
            {
                'name': 'AI Integration Partnership',
                'email': 'partner@cognito.ai',
                'company': 'Cognito AI',
                'score': 90,
                'status': 'Contacted',
                'stage': 'Proposal',
                'value': 550000,
                'owner': 'alex_rivera',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 88,
                'revenue': 550000
            },
            {
                'name': 'Global Logistics V2',
                'email': 'ops@skyfreight.com',
                'company': 'SkyFreight',
                'score': 70,
                'status': 'Contacted',
                'stage': 'Negotiation',
                'value': 420000,
                'owner': 'sarah_chen',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 68,
                'revenue': 420000
            },
            {
                'name': 'Retail Supply Chain',
                'email': 'logistics@vanguard.com',
                'company': 'Vanguard Retail',
                'score': 95,
                'status': 'Qualified',
                'stage': 'Won',
                'value': 680000,
                'owner': 'alex_rivera',
                'avatar': '',
                'lifecycle': 'Prospect',
                'health': 94,
                'revenue': 680000
            },
            {
                'name': 'Data Center Cooling',
                'email': 'facilities@arctictech.com',
                'company': 'Arctic Tech',
                'score': 40,
                'status': 'Lost',
                'stage': 'Lost',
                'value': 210000,
                'owner': 'jordan_smith',
                'avatar': '',
                'lifecycle': 'Lost Lead',
                'health': 20,
                'revenue': 210000
            }
        ]

        leads = {}
        for ld in leads_data:
            lead = Lead.objects.create(
                organization=org,
                name=ld['name'],
                email=ld['email'],
                company=ld['company'],
                score=ld['score'],
                status=ld['status'],
                stage=ld['stage'],
                value=ld['value'],
                owner=profiles[ld['owner']],
                profile_image_url=ld['avatar'],
                lifecycle_stage=ld['lifecycle'],
                health_score=ld['health'],
                annual_revenue=ld['revenue']
            )
            leads[ld['name']] = lead

        self.stdout.write('Creating activities and tasks...')
        # Seed Sarah Jenkins' detail timeline
        sj = leads['Sarah Jenkins']
        Activity.objects.create(lead=sj, type='Email', description='Email Opened: "Contract Renewal Proposal Q3"', timestamp=timezone.now() - datetime.timedelta(hours=2))
        Activity.objects.create(lead=sj, type='Call', description='Inbound Call: 15 min discovery session', timestamp=timezone.now() - datetime.timedelta(days=1))
        Activity.objects.create(lead=sj, type='Meeting', description='File Downloaded: Tech_Specs_v2.pdf', timestamp=timezone.now() - datetime.timedelta(days=3))
        
        # Tasks for Sarah Jenkins
        Task.objects.create(lead=sj, description='Review Renewal Quote', due_date=timezone.now().date(), priority='High')
        Task.objects.create(lead=sj, description='Follow up on Tech Specs', due_date=timezone.now().date() + datetime.timedelta(days=7), priority='Medium')

        # Other mock tasks and activities
        for l_name, lead in leads.items():
            if l_name != 'Sarah Jenkins':
                Activity.objects.create(
                    lead=lead,
                    type='Creation',
                    description=f"Lead created with starting stage '{lead.stage}'."
                )
                if lead.score > 85:
                    Task.objects.create(
                        lead=lead,
                        description="Initial high score follow-up",
                        due_date=timezone.now().date() + datetime.timedelta(days=2),
                        priority='High'
                    )

        self.stdout.write('Creating upcoming meetings...')
        # Upcoming meetings
        Meeting.objects.create(organization=org, title="Strategic Q4 Planning", date_time=timezone.now() + datetime.timedelta(days=1, hours=2), location="Boardroom")
        Meeting.objects.create(organization=org, title="Client Onboarding", date_time=timezone.now() + datetime.timedelta(days=2, hours=5), location="Zoom")
        Meeting.objects.create(organization=org, title="Sales Weekly Sync", date_time=timezone.now() + datetime.timedelta(days=3, hours=1), location="Room 302")

        self.stdout.write(self.style.SUCCESS('Successfully seeded database with premium data.'))
        self.stdout.write(self.style.WARNING("Default passwords for all users: 'password123'"))
