from django.shortcuts import render, redirect, get_object_or_404
from .models import Group, Student, Attendance, Payment
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q




@login_required
def group_attendance_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    students = group.students.all()
    
    if request.method == "POST":
        for student in students:
            # Checkbox holati
            status = request.POST.get(f'attendance_{student.id}') == 'on'
            # Sabab va Izoh
            reason = request.POST.get(f'reason_{student.id}')
            comment = request.POST.get(f'comment_{student.id}', "")

            # Davomatni saqlash yoki yangilash
            Attendance.objects.update_or_create(
                student=student, 
                group=group, 
                date=timezone.now().date(),
                defaults={
                    'is_present': status,
                    'reason_type': reason if not status else None,
                    'comment': comment if not status else ""
                }
            )
            
            # SMS yuborish (faqat sababsiz bo'lsa yuborishni sozlasa ham bo'ladi)
            if not status and reason == 'sababsiz':
                send_absent_sms(student.phone, student.full_name)
                
        return redirect('dashboard')

    # 3 marta dars qoldirganlarni dashboardda chiqarish uchun mantiqni 
    # alohida dashboard viewda yozish tavsiya etiladi.
    return render(request, 'attendance.html', {'group': group, 'students': students})

def send_absent_sms(phone, name):
    # Bu yerda SMS yuborish kodi bo'ladi
    print(f"SMS: {name} darsga kelmadi. Tel: {phone}")
from django.utils import timezone
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import timedelta
from .models import Student, Payment

from django.contrib import messages

def student_payment(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    group_price = student.group.price  # Guruhning belgilangan narxi

    if request.method == "POST":
        try:
            amount = int(float(request.POST.get('amount')))
        except (ValueError, TypeError):
            amount = 0
            
        payment_type = request.POST.get('payment_type')
        custom_date = request.POST.get('pay_until')

        # 1. To'lovni saqlash
        Payment.objects.create(
            student=student,
            amount=amount,
            payment_type=payment_type
        )

        # 2. Eskini unutish va yangi balansni o'rnatish
        # Siz aytgandek: eski balansni 0 qilib, yangi to'lovni hisoblaymiz
        student.balance = amount 

        # 3. Xabarnoma va Muddat mantiqi
        if amount < group_price:
            difference = group_price - amount
            messages.warning(request, f"Siz {amount} so'm to'lov qildingiz. To'liq kurs uchun yana {difference} so'm to'lashingiz kerak.")
        else:
            messages.success(request, f"To'lov muvaffaqiyatli qabul qilindi: {amount} so'm.")

        # 4. Sana mantiqi
        if custom_date:
            student.pay_until = custom_date
        elif amount >= group_price:
            # Agar to'liq to'lov bo'lsa, muddatni bugundan boshlab 30 kunga yangilaymiz
            student.pay_until = timezone.now().date() + timedelta(days=30)

        student.save()
        return redirect('student_list')

    return render(request, 'add_payment.html', {'student': student})


from django.shortcuts import render, get_object_or_404, redirect
from .models import Student, Teacher, Group, Attendance, Payment
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from django.contrib import messages # Xabarlar uchun

def dashboard(request):
    # 1. QO'LDA TEKSHIRISH (Security Check)
    # Birinchi: Foydalanuvchi login qilganmi?
    if not request.user.is_authenticated:
        return redirect('login') # Login qilmagan bo'lsa, srazu login sahifasiga
    
    # Ikkinchi: Foydalanuvchi adminmi (superuser)?
    if not request.user.is_superuser:
        # Agar login qilgan bo'lsa-yu, lekin admin bo'lmasa (masalan ustoz bo'lsa)
        # Uni o'ziga tegishli sahifaga yoki login sahifasiga haydaymiz
        return redirect('login') 

    # --- AGAR TEKSHIRUVDAN O'TSA, KEYIN PASTDAGI KODLAR ISHLAYDI ---

    today = timezone.now().date()
    five_days_later = today + timedelta(days=5)
    
    # 1. Surunkali dars qoldirganlar (Ketma-ket 3 ta)
    chronic_absent_students = []
    # Bazani ortiqcha yuklamaslik uchun Student.objects.all() o'rniga filter ishlatsa ham bo'ladi
    all_students = Student.objects.all()
    for student in all_students:
        last_3 = Attendance.objects.filter(student=student).order_by('-date')[:3]
        if last_3.count() == 3 and all(not att.is_present for att in last_3):
            chronic_absent_students.append(student)

    # 2. Bugungi davomat yozuvlari
    absent_records = Attendance.objects.filter(date=today, is_present=False)
    
    # Kelmaganlarni turlarga ajratish
    absent_unexcused = absent_records.filter(reason_type='sababsiz')
    absent_excused = absent_records.filter(reason_type='sababli')
    present_today = Attendance.objects.filter(date=today, is_present=True)

    # 3. To'lovlar mantiqi
    warning_students = Student.objects.filter(
        pay_until__lte=five_days_later, 
        pay_until__gte=today
    )
    debtors_count = Student.objects.filter(pay_until__lt=today).count()

    context = {
        'students_count': all_students.count(),
        'teachers_count': Teacher.objects.count(),
        'groups_count': Group.objects.count(),
        
        # Davomat ma'lumotlari
        'absent_unexcused': absent_unexcused,
        'absent_excused': absent_excused,
        'present_today': present_today,
        'chronic_absent_students': chronic_absent_students,
        
        # To'lov ma'lumotlari
        'warning_students': warning_students,
        'debtors_count': debtors_count,
        'today': today,
    }
    return render(request, 'dashboard.html', context)

# 2. O'quvchilar ro'yxati
@login_required
def student_list(request):
    students = Student.objects.all()
    return render(request, 'students.html', {'students': students})

# 3. Ustozlar ro'yxati
@login_required
def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, 'teachers.html', {'teachers': teachers})

# 4. Guruhlar ro'yxati
@login_required
def group_list(request):
    groups = Group.objects.all()
    return render(request, 'groups.html', {'groups': groups})

# 5. Davomat hisoboti (Bugun kim keldi, kim kelmadi)
@login_required
def attendance_report(request):
    today = timezone.now().date()
    absent = Attendance.objects.filter(date=today, is_present=False)
    present = Attendance.objects.filter(date=today, is_present=True)
    return render(request, 'attendance_report.html', {
        'absent': absent, 
        'present': present, 
        'today': today
    })


from django.shortcuts import render, get_object_or_404
from .models import Student, Payment, Attendance
@login_required
def student_detail(request, student_id):
    # O'quvchini ID bo'yicha topamiz, agar yo'q bo'lsa 404 xatolik beradi
    student = get_object_or_404(Student, id=student_id)
    
    # O'quvchining barcha to'lovlarini eng oxirgisidan boshlab olamiz
    payments = student.payments.all().order_by('-date')
    
    # O'quvchining davomat tarixini olamiz
    attendances = Attendance.objects.filter(student=student).order_by('-date')
    
    context = {
        'student': student,
        'payments': payments,
        'attendances': attendances,
    }
    
    return render(request, 'student_detail.html', context)


from django.shortcuts import render, redirect, get_object_or_404
from .forms import StudentForm, TeacherForm, GroupForm, SimpleTeacherForm
from .models import Student, Teacher, Group

# --- O'QUVCHILAR UCHUN ---
@login_required
def student_create(request):
    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'form_template.html', {'form': form, 'title': "Yangi o'quvchi qo'shish"})
@login_required
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'form_template.html', {'form': form, 'title': "O'quvchini tahrirlash"})
@login_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        student.delete()
        return redirect('student_list')
    return render(request, 'confirm_delete.html', {'obj': student})

# --- GURUHLAR UCHUN ---
@login_required
def group_create(request):
    if request.method == "POST":
        form = GroupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('group_list')
    form = GroupForm()
    return render(request, 'form_template.html', {'form': form, 'title': "Yangi guruh ochish"})


# Ustozlar ro'yxati
@login_required
def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, 'teachers.html', {'teachers': teachers})

# Ustoz qo'shish
@login_required
def teacher_create(request):
    form = TeacherForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect('teacher_list')
    return render(request, 'form_template.html', {'form': form, 'title': "Yangi ustoz"})

# Ustozni tahrirlash
@login_required
def teacher_update(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    form = TeacherForm(request.POST or None, instance=teacher)
    if form.is_valid():
        form.save()
        return redirect('teacher_list')
    return render(request, 'form_template.html', {'form': form, 'title': "Ustoz ma'lumotlarini tahrirlash"})

# Ustozni o'chirish
@login_required
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == "POST":
        teacher.delete()
        return redirect('teacher_list')
    return render(request, 'confirm_delete.html', {'obj': teacher})





@login_required
def move_student(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    groups = Group.objects.exclude(id=student.group.id) # Hozirgi guruhidan boshqa hamma guruhlar

    if request.method == "POST":
        new_group_id = request.POST.get('new_group')
        new_group = get_object_or_404(Group, id=new_group_id)
        
        # O'quvchini yangi guruhga biriktirish
        student.group = new_group
        student.save()
        
        return redirect('student_detail', student_id=student.id)

    return render(request, 'move_student.html', {
        'student': student,
        'groups': groups
    })

@login_required
def change_group_teacher(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    teachers = Teacher.objects.all()

    if request.method == "POST":
        new_teacher_id = request.POST.get('new_teacher')
        new_teacher = get_object_or_404(Teacher, id=new_teacher_id)
        
        group.teacher = new_teacher
        group.save()
        
        return redirect('group_list')

    return render(request, 'change_teacher.html', {
        'group': group,
        'teachers': teachers
    })
@login_required
def teacher_create_simple(request):
    if request.method == "POST":
        form = SimpleTeacherForm(request.POST)
        if form.is_valid():
            # 1. User yaratish
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
                first_name=form.cleaned_data['first_name']
            )
            # 2. Teacher profilini yaratish
            teacher = Teacher.objects.create(
                user=user,
                phone=form.cleaned_data['phone']
            )
            
            # 3. Guruhga ustozni biriktirish (Ixtiyoriy qism)
            group = form.cleaned_data.get('group') # get ishlatish xavfsizroq
            if group is not None:  # Agar guruh tanlangan bo'lsagina ishlaydi
                group.teacher = teacher
                group.save()
            
            return redirect('teacher_list')
    else:
        form = SimpleTeacherForm()
    
    return render(request, 'teacher_add_custom.html', {'form': form})

