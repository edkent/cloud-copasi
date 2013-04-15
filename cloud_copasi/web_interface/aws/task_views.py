#-------------------------------------------------------------------------------
# Cloud-COPASI
# Copyright (c) 2013 Edward Kent.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#-------------------------------------------------------------------------------
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseServerError
from django.views.generic import TemplateView, RedirectView, View, FormView
from django.views.generic.edit import FormMixin, ProcessFormView
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse_lazy
from django import forms
from cloud_copasi.web_interface.views import RestrictedView, DefaultView, RestrictedFormView
from cloud_copasi.web_interface.models import AWSAccessKey, VPC, CondorPool, CondorJob, Task
from cloud_copasi.web_interface import models, aws
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required, permission_required
import sys
from cloud_copasi.web_interface.account.account_views import MyAccountView
from django.contrib.auth.forms import PasswordChangeForm
from boto.vpc import VPCConnection
from boto.ec2 import EC2Connection
from cloud_copasi.web_interface.aws import vpc_tools, task_tools
from cloud_copasi.web_interface import form_tools
import tempfile, os
from cloud_copasi import settings, copasi
from cloud_copasi.copasi.model import CopasiModel


class NewTaskForm(forms.Form):
    name = forms.CharField()
    task_type = forms.ChoiceField(choices=copasi.task_types)
    access_key = form_tools.NameChoiceField(queryset=None, initial=0)
    model_file = forms.FileField()
    compute_pool = form_tools.NameChoiceField(queryset=None, initial=0)
    
    minimum_repeats = forms.IntegerField(required=False)
    maximum_repeats = forms.IntegerField(required=False)
    
    
    def __init__(self, user, *args, **kwargs):
        super(NewTaskForm, self).__init__(*args, **kwargs)
        self.user = user

        access_keys = AWSAccessKey.objects.filter(user=self.user).filter(vpc__isnull=False)
        self.fields['access_key'].queryset = access_keys
        
        condor_pools = CondorPool.objects.filter(vpc__access_key__user = user)
        self.fields['compute_pool'].queryset = condor_pools
        

class NewTaskView(RestrictedFormView):
    template_name = 'tasks/task_new.html'
    page_title = 'New task'
    form_class = NewTaskForm
    
    def get_form_kwargs(self):
        kwargs = super(NewTaskView, self).get_form_kwargs()
        kwargs['user']=self.request.user
        return kwargs
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        #Ensure we have at least 1 running condor pool
        pools = CondorPool.objects.filter(vpc__access_key__user=request.user)
        if pools.count() == 0:
            request.session['errors']=[('No running compute pools', 'You must have at least 1 running compute pool before you can submit a job')]
            return HttpResponseRedirect(reverse_lazy('pool_status'))
        return super(NewTaskView,self).dispatch(request, *args, **kwargs)
    
    def form_valid(self, form,  *args, **kwargs):
        access_key = form.cleaned_data['access_key']
        compute_pool = form.cleaned_data['compute_pool']
        request = self.request

        assert access_key.user == request.user
        assert compute_pool.vpc.access_key == access_key
        
        ########################################################################
        #Process the uploaded copasi file (and other files?) and create a list
        #of files to upload to s3
        ########################################################################
        
        #Handle uploaded files...
        #Ensure the directory we're adding the file to exists
        if not os.path.exists(settings.STORAGE_DIR):
            os.mkdir(settings.STORAGE_DIR)
        
        working_dir = tempfile.mkdtemp(dir=settings.STORAGE_DIR)
        model_file = request.FILES['model_file']
        
        full_filename = os.path.join(working_dir, model_file.name)

        form_tools.handle_uploaded_file(model_file, full_filename)
        
        print >> sys.stderr, full_filename
        
        ##TODO:Do this for any data files too
        #Check the file is valid for the task type
        #
        
#------------------------------------------------------------------------------ 
        #Process the model file and create the neccesary files needed for
        #submitting the condor jobs
#------------------------------------------------------------------------------ 
        
        if form.cleaned_data['task_type'] != 'SO':
            raise Exception('Only the sensitivity optimisation task is currently implemented')
        
        copasi_model = CopasiModel(full_filename)
        isvalid = copasi_model.is_valid(form.cleaned_data['task_type'])
        if isvalid != True:
            raise Exception(isvalid)
        
        #If no load balancing step required:
        model_files = copasi_model.prepare_so_task()
        condor_job_info_list = copasi_model.prepare_so_condor_jobs()
        
        task = Task()
        task.name = form.cleaned_data['name']
        task.condor_pool = form.cleaned_data['compute_pool']
        task.task_type = form.cleaned_data['task_type']
        task.min_runs = form.cleaned_data['minimum_repeats']
        task.max_runs = form.cleaned_data['maximum_repeats']
        task.original_model = full_filename
        task.save()
        
        for condor_job_info in condor_job_info_list:
            condor_job = CondorJob()
            condor_job.task = task
            condor_job.spec_file = condor_job_info['spec_file']
            condor_job.std_output_file = condor_job_info['std_output_file']
            condor_job.std_error_file  = condor_job_info['std_error_file']
            condor_job.log_file = condor_job_info['log_file']
            condor_job.job_output = condor_job_info['job_output']
            condor_job.copasi_file = condor_job_info['copasi_file']
            condor_job.queue_status='C' # Not copied
            
            condor_job.save()
            
            
        
#------------------------------------------------------------------------------ 
#Copy the files over to S3
#------------------------------------------------------------------------------ 
        
        file_keys, spec_keys = task_tools.store_to_outgoing_bucket(task)
        
        
#        ####################################################################
#        Notify the pool queue that a new task has been submitted
#        ####################################################################

        task_tools.notify_new_task(task, file_keys, spec_keys)
        
        #Update the task queue status
        task.status = 'Q'
        #except:
        #unto anything performed here and delete files
        
        return HttpResponseRedirect(reverse_lazy('my_account'))
    
class JobNewView(RestrictedView):
    pass
